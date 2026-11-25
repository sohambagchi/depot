package com.sohambagchi.depot;

import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import java.io.File;
import java.util.concurrent.TimeUnit;

/**
 * Updates for this app from depot (see android-emu's depot/PROTOCOL.md).
 *
 * Including the library is enough: a periodic job checks for a newer build, downloads and
 * verifies it, and posts a notification that installs it on tap. These methods are for apps
 * that also want an in-app "check" or "install" control.
 */
public final class Depot {
    static final String TAG = "depot";
    static final String PREFS = "depot";
    static final long PERIOD_MS = TimeUnit.HOURS.toMillis(6);
    static final long CHECK_ON_START_AFTER_MS = TimeUnit.HOURS.toMillis(1);
    private static final int JOB_PERIODIC = 0x64657001;
    private static final int JOB_NOW = 0x64657002;

    private Depot() {}

    /** A downloaded, verified update waiting to be installed. */
    public static final class Update {
        public final long code;
        public final String name;
        public final String notes;
        final File file;

        Update(long code, String name, String notes, File file) {
            this.code = code;
            this.name = name;
            this.notes = notes;
            this.file = file;
        }
    }

    /** Checks for an update as soon as there is a network, off the main thread. */
    public static void checkNow(Context context) {
        Context app = context.getApplicationContext();
        scheduler(app).schedule(new JobInfo.Builder(JOB_NOW, new ComponentName(app, CheckJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .build());
    }

    /** The update waiting to be installed, or null. */
    public static Update pending(Context context) {
        SharedPreferences p = prefs(context);
        long code = p.getLong("pending_code", 0);
        String path = p.getString("pending_path", null);
        if (code <= Checker.installedCode(context) || path == null || !new File(path).isFile()) return null;
        return new Update(code, p.getString("pending_name", ""), p.getString("pending_notes", ""), new File(path));
    }

    /** Starts the install of the pending update (asking for the install permission first if needed). */
    public static Intent installIntent(Context context) {
        return new Intent(context, InstallActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    }

    /** Called when the process starts: keeps the periodic job scheduled and checks if it has been a while. */
    static void onProcessStart(Context app) {
        JobScheduler js = scheduler(app);
        if (js.getPendingJob(JOB_PERIODIC) == null) {
            js.schedule(new JobInfo.Builder(JOB_PERIODIC, new ComponentName(app, CheckJob.class))
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                    .setPeriodic(PERIOD_MS, TimeUnit.HOURS.toMillis(1))
                    .setPersisted(true)
                    .build());
        }
        Checker.dropInstalled(app);
        if (System.currentTimeMillis() - prefs(app).getLong("last_check", 0) > CHECK_ON_START_AFTER_MS) {
            checkNow(app);
        }
    }

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static JobScheduler scheduler(Context context) {
        JobScheduler js = context.getSystemService(JobScheduler.class);
        // A namespace keeps depot's job ids clear of the app's own (WorkManager uses JobScheduler too).
        return Build.VERSION.SDK_INT >= 34 ? js.forNamespace("depot") : js;
    }
}
