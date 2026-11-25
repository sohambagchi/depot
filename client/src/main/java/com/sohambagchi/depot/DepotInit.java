package com.sohambagchi.depot;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.net.Uri;
import android.util.Log;

/** Runs once per process start, before Application.onCreate, so the app needs no setup code. */
public final class DepotInit extends ContentProvider {
    @Override
    public boolean onCreate() {
        try {
            Depot.onProcessStart(getContext().getApplicationContext());
        } catch (RuntimeException e) { // never take the app down with it
            Log.w(Depot.TAG, "could not schedule update checks", e);
        }
        return true;
    }

    @Override public Cursor query(Uri u, String[] p, String s, String[] a, String o) { return null; }
    @Override public String getType(Uri u) { return null; }
    @Override public Uri insert(Uri u, ContentValues v) { return null; }
    @Override public int delete(Uri u, String s, String[] a) { return 0; }
    @Override public int update(Uri u, ContentValues v, String s, String[] a) { return 0; }
}
