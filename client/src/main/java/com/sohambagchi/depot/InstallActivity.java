package com.sohambagchi.depot;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Log;
import android.widget.Toast;

import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * Installs the pending update through a PackageInstaller session. It has no UI of its own: it
 * stays (invisible) on top until the installer answers, so it may start the system's
 * confirmation screen. A successful self-update ends this process.
 */
public final class InstallActivity extends Activity {
    private static final String ACTION_STATUS = "com.sohambagchi.depot.INSTALL_STATUS";

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        if (saved == null) handle(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handle(intent);
    }

    private void handle(Intent intent) {
        if (ACTION_STATUS.equals(intent.getAction())) {
            onStatus(intent);
            return;
        }
        Depot.Update u = Depot.pending(this);
        if (u == null) {
            toast("No update is waiting");
            finish();
            return;
        }
        if (!getPackageManager().canRequestPackageInstalls()) {
            toast("Allow installs from this app, then tap the update notification again");
            startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + getPackageName())));
            finish();
            return;
        }
        toast("Installing " + u.name);
        new Thread(() -> {
            try {
                commit(u);
            } catch (IOException | RuntimeException e) {
                Log.w(Depot.TAG, "install failed", e);
                runOnUiThread(() -> {
                    toast("Update failed: " + e.getMessage());
                    finish();
                });
            }
        }, "depot-install").start();
    }

    private void commit(Depot.Update u) throws IOException {
        PackageInstaller installer = getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(
                PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(getPackageName());
        params.setSize(u.file.length());
        if (Build.VERSION.SDK_INT >= 31) {
            // An app updating itself may skip the confirmation; the tap was the confirmation.
            params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED);
        }
        int id = installer.createSession(params);
        try (PackageInstaller.Session session = installer.openSession(id)) {
            try (InputStream in = new FileInputStream(u.file);
                 OutputStream out = session.openWrite("base.apk", 0, u.file.length())) {
                byte[] buf = new byte[64 * 1024];
                for (int r; (r = in.read(buf)) > 0; ) out.write(buf, 0, r);
                session.fsync(out);
            }
            Intent status = new Intent(this, InstallActivity.class).setAction(ACTION_STATUS);
            PendingIntent pi = PendingIntent.getActivity(this, id, status,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE);
            session.commit(pi.getIntentSender());
        } catch (IOException | RuntimeException e) {
            installer.abandonSession(id);
            throw e;
        }
    }

    @SuppressWarnings("deprecation")
    private void onStatus(Intent intent) {
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirm = Build.VERSION.SDK_INT >= 33
                    ? intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent.class)
                    : intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirm != null) {
                startActivity(confirm);
                return; // the next status arrives here once the user answers
            }
        }
        if (status == PackageInstaller.STATUS_SUCCESS) {
            Checker.dropInstalled(this);
        } else {
            String msg = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
            Log.w(Depot.TAG, "install ended with status " + status + ": " + msg);
            if (status != PackageInstaller.STATUS_FAILURE_ABORTED) toast("Update failed: " + msg);
        }
        finish();
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_LONG).show();
    }
}
