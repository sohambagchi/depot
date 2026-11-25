package com.sohambagchi.depot;

import android.app.Activity;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.content.res.TypedArray;
import android.graphics.Insets;
import android.os.Bundle;
import android.text.format.DateUtils;
import android.util.Log;
import android.util.TypedValue;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.security.GeneralSecurityException;

/**
 * The "App updates" screen an app opens from its "Check for updates" item
 * ({@link Depot#updatesIntent}). It checks as soon as it opens, says what it found, and offers
 * the install when an update is ready. Built in code so the library carries no layouts.
 */
public final class UpdatesActivity extends Activity {
    private TextView status, notes, lastChecked;
    private Button install, check;
    private boolean checking;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        setContentView(layout());
        boolean night = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
                == Configuration.UI_MODE_NIGHT_YES;
        int light = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
        getWindow().getInsetsController().setSystemBarsAppearance(night ? 0 : light, light);
        // Recreated (a rotation or a theme change): keep what the screen said, and redo a check
        // that was still running, since its result would go to the old screen.
        if (saved == null || saved.getBoolean("checking")) startCheck();
        else showPending(saved.getString("status"));
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        out.putBoolean("checking", checking);
        out.putString("status", status.getText().toString());
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (!checking) showPending(null); // an install may have finished or failed meanwhile
    }

    private View layout() {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);

        TextView title = text(28, "App updates");
        title.setPadding(0, 0, 0, dp(16));
        PackageInfo info = installed();
        CharSequence label = getApplicationInfo().loadLabel(getPackageManager());
        TextView version = text(16, label + " " + info.versionName + " (" + info.getLongVersionCode() + ")");
        status = text(18, "");
        status.setPadding(0, dp(24), 0, 0);
        notes = text(15, "");
        notes.setPadding(0, dp(8), 0, 0);
        install = new Button(this);
        install.setBackgroundTintList(android.content.res.ColorStateList.valueOf(themeColor(android.R.attr.colorAccent)));
        install.setTextColor(themeColor(android.R.attr.textColorPrimaryInverse));
        install.setOnClickListener(v -> startActivity(Depot.installIntent(this)));
        check = new Button(this);
        check.setText("Check again");
        check.setOnClickListener(v -> startCheck());
        LinearLayout buttons = new LinearLayout(this);
        buttons.setPadding(0, dp(16), 0, 0);
        buttons.addView(install);
        buttons.addView(check);
        LinearLayout.LayoutParams gap = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        gap.setMarginStart(dp(8));
        check.setLayoutParams(gap);
        lastChecked = text(13, "");
        lastChecked.setTextColor(themeColor(android.R.attr.textColorSecondary));
        lastChecked.setPadding(0, dp(16), 0, 0);
        TextView auto = text(13, "Updates are also checked automatically every few hours.");
        auto.setTextColor(themeColor(android.R.attr.textColorSecondary));
        auto.setPadding(0, dp(4), 0, 0);
        for (View v : new View[] {title, version, status, notes, buttons, lastChecked, auto}) col.addView(v);

        ScrollView scroll = new ScrollView(this);
        scroll.setClipToPadding(false);
        scroll.addView(col);
        int pad = dp(24);
        scroll.setOnApplyWindowInsetsListener((v, insets) -> {
            Insets i = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            v.setPadding(pad + i.left, pad + i.top, pad + i.right, pad + i.bottom);
            return WindowInsets.CONSUMED;
        });
        return scroll;
    }

    private void startCheck() {
        if (checking) return;
        checking = true;
        check.setEnabled(false);
        status.setText("Checking for updates…");
        notes.setVisibility(View.GONE);
        install.setVisibility(View.GONE);
        new Thread(() -> {
            String message;
            try {
                message = describe(Checker.run(getApplicationContext(), false));
            } catch (IOException | GeneralSecurityException | RuntimeException e) {
                Log.w(Depot.TAG, "update check failed", e);
                message = describe(e);
            }
            String result = message;
            runOnUiThread(() -> {
                if (isDestroyed()) return;
                checking = false;
                check.setEnabled(true);
                showPending(result);
            });
        }, "depot-check-now").start();
    }

    /** Shows the pending update if there is one, else `message` (or leaves the status as it is). */
    private void showPending(String message) {
        Depot.Update u = Depot.pending(this);
        if (u != null) {
            status.setText(u.name + " is ready to install.");
            install.setText("Install " + u.name);
            install.setVisibility(View.VISIBLE);
            notes.setText(u.notes);
            notes.setVisibility(u.notes.isEmpty() ? View.GONE : View.VISIBLE);
        } else {
            install.setVisibility(View.GONE);
            notes.setVisibility(View.GONE);
            if (message != null) status.setText(message);
        }
        long last = Depot.prefs(this).getLong("last_success", 0);
        lastChecked.setText(last == 0 ? "Not checked yet."
                : "Last checked " + DateUtils.getRelativeTimeSpanString(last, System.currentTimeMillis(),
                        DateUtils.MINUTE_IN_MILLIS) + ".");
    }

    private static String describe(Checker.Outcome o) {
        switch (o) {
            case UP_TO_DATE: return "Up to date.";
            case READY: return "An update is ready."; // replaced by showPending's own text
            case NOTHING_PUBLISHED: return "depot has no builds of this app yet.";
            case OTHER_SIGNER: return "depot's newest build is signed by a different key, so it can't update this app.";
            default: return "This build doesn't check for updates (it was built without depot's address).";
        }
    }

    private static String describe(Exception e) {
        if (e instanceof Checker.NotEnrolled) {
            return "This device isn't enrolled for updates yet. Turn on Tailscale, then check again.";
        }
        if (e instanceof UnknownHostException || e instanceof ConnectException || e instanceof SocketTimeoutException) {
            return "Can't reach depot. Connect to home Wi-Fi or turn on Tailscale, then check again.";
        }
        if (e instanceof GeneralSecurityException) return "Couldn't use this device's update key: " + e.getMessage();
        return "The check failed: " + e.getMessage();
    }

    private PackageInfo installed() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0);
        } catch (PackageManager.NameNotFoundException e) {
            throw new IllegalStateException(e);
        }
    }

    private TextView text(float sp, String s) {
        TextView t = new TextView(this);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(themeColor(android.R.attr.textColorPrimary));
        t.setText(s);
        return t;
    }

    private int themeColor(int attr) {
        TypedArray a = obtainStyledAttributes(new int[] {attr});
        try {
            return a.getColor(0, 0);
        } finally {
            a.recycle();
        }
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
