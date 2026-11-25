package com.sohambagchi.depot;

import android.app.job.JobParameters;
import android.app.job.JobService;
import android.util.Log;

/** The scheduled update check; network work runs on its own thread. */
public final class CheckJob extends JobService {
    @Override
    public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            try {
                Checker.run(getApplicationContext());
            } catch (Exception e) {
                Log.w(Depot.TAG, "update check failed: " + e);
            }
            jobFinished(params, false); // a periodic job runs again anyway; a one-off check isn't retried
        }, "depot-check").start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return false;
    }
}
