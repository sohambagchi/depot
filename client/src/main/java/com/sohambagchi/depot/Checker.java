package com.sohambagchi.depot;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.SigningInfo;
import android.os.Build;
import android.util.Log;

import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/** One update check: authenticate, ask for the latest release, download and verify it, notify. */
final class Checker {
    private static final String CHANNEL = "depot-updates";
    private static final int NOTIFICATION = 0x64657003;

    private Checker() {}

    static synchronized void run(Context ctx) throws IOException, GeneralSecurityException {
        SharedPreferences p = Depot.prefs(ctx);
        p.edit().putLong("last_check", System.currentTimeMillis()).apply();
        dropInstalled(ctx);
        if (BuildConfig.DEPOT_URLS.isEmpty()) {
            Log.w(Depot.TAG, "built without DEPOT_URLS; not checking");
            return;
        }
        Api api = new Api(BuildConfig.DEPOT_URLS);
        String token = session(ctx, api, p);
        String pkg = ctx.getPackageName();

        JSONObject rel;
        try {
            rel = api.json("GET", "/v1/apps/" + pkg + "/latest", null, token);
        } catch (Api.HttpError e) {
            if (e.status == 404) {
                Log.i(Depot.TAG, "nothing published for " + pkg);
                return;
            }
            throw e;
        }
        long code = rel.optLong("code");
        String name = rel.optString("name");
        long installed = installedCode(ctx);
        if (code <= installed) {
            Log.i(Depot.TAG, "up to date (" + installed + ", latest " + code + ")");
            return;
        }
        String signer = rel.optString("signer");
        if (!signer.equalsIgnoreCase(installedSigner(ctx))) {
            Log.w(Depot.TAG, name + " (" + code + ") is signed by another key; not offering it");
            return;
        }

        Depot.Update pending = Depot.pending(ctx);
        if (pending == null || pending.code != code) {
            File dir = new File(ctx.getNoBackupFilesDir(), "depot");
            if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("cannot create " + dir);
            File part = new File(dir, code + ".apk.part");
            MessageDigest sha = sha256();
            String url = rel.optString("url", "/v1/apps/" + pkg + "/" + code + ".apk");
            long size = api.download(url, token, part, sha);
            String hash = hex(sha.digest());
            if (size != rel.optLong("size") || !hash.equalsIgnoreCase(rel.optString("sha256"))) {
                part.delete();
                throw new IOException("download of " + code + " does not match its size or hash");
            }
            String problem = checkArchive(ctx, part, code, signer);
            if (problem != null) {
                part.delete();
                throw new IOException("downloaded APK " + problem);
            }
            File apk = new File(dir, code + ".apk");
            if (!part.renameTo(apk)) throw new IOException("cannot rename " + part);
            File[] old = dir.listFiles();
            if (old != null) for (File f : old) if (!f.equals(apk)) f.delete();
            p.edit().putLong("pending_code", code).putString("pending_name", name)
                    .putString("pending_notes", rel.optString("notes")).putString("pending_path", apk.getPath())
                    .apply();
            pending = Depot.pending(ctx);
            Log.i(Depot.TAG, "downloaded " + name + " (" + code + ")");
        }
        if (pending != null && p.getLong("notified_code", 0) != code) {
            notifyReady(ctx, pending);
            p.edit().putLong("notified_code", code).apply();
        }
    }

    /** A bearer token, enrolling first (over the tailnet) when this app has no device id yet. */
    private static String session(Context ctx, Api api, SharedPreferences p) throws IOException, GeneralSecurityException {
        for (int attempt = 0; ; attempt++) {
            String device = p.getString("device", null);
            if (device == null) {
                JSONObject body = new JSONObject();
                try {
                    body.put("name", Build.MODEL + " / " + ctx.getPackageName());
                    body.put("key", DeviceKey.publicKey());
                } catch (org.json.JSONException e) {
                    throw new IllegalStateException(e);
                }
                device = api.enroll(body).optString("device");
                p.edit().putString("device", device).apply();
                Log.i(Depot.TAG, "enrolled as " + device);
            }
            String nonce = api.json("GET", "/v1/challenge", null, null).optString("nonce");
            JSONObject req = new JSONObject();
            try {
                req.put("device", device).put("nonce", nonce).put("sig", DeviceKey.answer(nonce, device));
            } catch (org.json.JSONException e) {
                throw new IllegalStateException(e);
            }
            try {
                return api.json("POST", "/v1/session", req, null).getString("token");
            } catch (Api.HttpError e) {
                if (e.status != 401 || attempt > 0) throw e;
                Log.i(Depot.TAG, "depot no longer knows " + device + "; enrolling again");
                p.edit().remove("device").apply();
            } catch (org.json.JSONException e) {
                throw new IOException("session without a token", e);
            }
        }
    }

    /** Null if the APK is this app at `code`, signed by `signer`; otherwise what is wrong with it. */
    private static String checkArchive(Context ctx, File apk, long code, String signer) {
        PackageManager pm = ctx.getPackageManager();
        PackageInfo info = pm.getPackageArchiveInfo(apk.getPath(),
                PackageManager.GET_SIGNING_CERTIFICATES | PackageManager.GET_SIGNATURES);
        if (info == null) return "is not a readable package";
        if (!ctx.getPackageName().equals(info.packageName)) return "is " + info.packageName;
        if (info.getLongVersionCode() != code) return "has version code " + info.getLongVersionCode();
        String digest = signerDigest(info);
        if (digest == null) return "has no readable signer";
        if (!digest.equalsIgnoreCase(signer)) return "is signed by another key";
        return null;
    }

    static long installedCode(Context ctx) {
        try {
            return ctx.getPackageManager().getPackageInfo(ctx.getPackageName(), 0).getLongVersionCode();
        } catch (PackageManager.NameNotFoundException e) {
            throw new IllegalStateException(e);
        }
    }

    private static String installedSigner(Context ctx) {
        try {
            return signerDigest(ctx.getPackageManager().getPackageInfo(ctx.getPackageName(),
                    PackageManager.GET_SIGNING_CERTIFICATES));
        } catch (PackageManager.NameNotFoundException e) {
            throw new IllegalStateException(e);
        }
    }

    /** SHA-256 of the current signing certificate, as apksigner prints it; null if unknown or several. */
    @SuppressWarnings("deprecation")
    private static String signerDigest(PackageInfo info) {
        Signature[] sigs = null;
        SigningInfo si = info.signingInfo;
        if (si != null) sigs = si.hasMultipleSigners() ? null : si.getApkContentsSigners();
        else sigs = info.signatures; // archives on some releases fill only the old field
        if (sigs == null || sigs.length != 1) return null;
        return hex(sha256().digest(sigs[0].toByteArray()));
    }

    /** Forgets a pending update once it (or something newer) is installed. */
    static void dropInstalled(Context ctx) {
        SharedPreferences p = Depot.prefs(ctx);
        long code = p.getLong("pending_code", 0);
        if (code == 0 || code > installedCode(ctx)) return;
        String path = p.getString("pending_path", null);
        if (path != null) new File(path).delete();
        p.edit().remove("pending_code").remove("pending_name").remove("pending_notes").remove("pending_path").apply();
        ctx.getSystemService(NotificationManager.class).cancel(NOTIFICATION);
        Log.i(Depot.TAG, "update " + code + " is installed");
    }

    static void notifyReady(Context ctx, Depot.Update u) {
        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= 33
                && ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            Log.w(Depot.TAG, "update " + u.name + " is ready, but notifications are not allowed");
            return;
        }
        nm.createNotificationChannel(new NotificationChannel(CHANNEL, "App updates", NotificationManager.IMPORTANCE_DEFAULT));
        CharSequence label = ctx.getApplicationInfo().loadLabel(ctx.getPackageManager());
        PendingIntent tap = PendingIntent.getActivity(ctx, 0, Depot.installIntent(ctx),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification n = new Notification.Builder(ctx, CHANNEL)
                .setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentTitle(label + " " + u.name + " is ready")
                .setContentText("Tap to install")
                .setStyle(new Notification.BigTextStyle().bigText("Tap to install.\n" + u.notes))
                .setContentIntent(tap)
                .setOnlyAlertOnce(true)
                .build();
        nm.notify(NOTIFICATION, n);
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private static String hex(byte[] b) {
        StringBuilder s = new StringBuilder(b.length * 2);
        for (byte x : b) s.append(String.format("%02x", x));
        return s.toString();
    }
}
