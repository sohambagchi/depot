package com.sohambagchi.depot;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;

/**
 * HTTP to depot. The server has several addresses (home LAN first, then the tailnet); a request
 * goes to the one that answered last and falls through the rest when it can't connect.
 */
final class Api {
    static final class HttpError extends IOException {
        final int status;

        HttpError(int status, String message) {
            super("HTTP " + status + ": " + message);
            this.status = status;
        }
    }

    private final List<String> bases = new ArrayList<>();
    private int preferred = 0;

    Api(String urls) {
        for (String u : urls.split(",")) {
            u = u.trim();
            if (u.isEmpty()) continue;
            if (!u.contains("://")) u = "http://" + u;
            bases.add(u.replaceAll("/+$", ""));
        }
        if (bases.isEmpty()) throw new IllegalArgumentException("no depot URLs configured");
    }

    /** A JSON request; throws HttpError for any status but 2xx. */
    JSONObject json(String method, String path, JSONObject body, String token) throws IOException {
        IOException last = null;
        for (int i = 0; i < bases.size(); i++) {
            int b = (preferred + i) % bases.size();
            HttpURLConnection c = open(bases.get(b) + path, method, token);
            try {
                if (body != null) {
                    c.setDoOutput(true);
                    c.setRequestProperty("Content-Type", "application/json");
                    try (OutputStream out = c.getOutputStream()) {
                        out.write(body.toString().getBytes(StandardCharsets.UTF_8));
                    }
                }
                int status = c.getResponseCode();
                preferred = b;
                String text = readAll(status < 400 ? c.getInputStream() : c.getErrorStream());
                if (status / 100 != 2) throw new HttpError(status, errorText(text));
                return new JSONObject(text);
            } catch (HttpError e) {
                throw e;
            } catch (JSONException e) {
                throw new IOException("bad JSON from " + bases.get(b) + path, e);
            } catch (IOException e) { // can't reach this address: try the next
                last = e;
            } finally {
                c.disconnect();
            }
        }
        throw last;
    }

    /** Enrollment only works over the tailnet, so it tries every address until one accepts it. */
    JSONObject enroll(JSONObject body) throws IOException {
        IOException last = null;
        for (int i = 0; i < bases.size(); i++) {
            preferred = i;
            try {
                return json("POST", "/v1/enroll", body, null);
            } catch (IOException e) {
                last = e;
            }
        }
        throw last;
    }

    /** Streams a file to `out`, feeding `digest`; returns the byte count. */
    long download(String path, String token, File out, MessageDigest digest) throws IOException {
        HttpURLConnection c = open(bases.get(preferred) + path, "GET", token);
        c.setReadTimeout(60_000);
        try {
            int status = c.getResponseCode();
            if (status != 200) throw new HttpError(status, errorText(readAll(c.getErrorStream())));
            long n = 0;
            byte[] buf = new byte[64 * 1024];
            try (InputStream in = c.getInputStream(); OutputStream o = new FileOutputStream(out)) {
                for (int r; (r = in.read(buf)) > 0; ) {
                    o.write(buf, 0, r);
                    digest.update(buf, 0, r);
                    n += r;
                }
            }
            return n;
        } finally {
            c.disconnect();
        }
    }

    private static HttpURLConnection open(String url, String method, String token) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestMethod(method);
        c.setConnectTimeout(4_000);
        c.setReadTimeout(20_000);
        c.setUseCaches(false);
        if (token != null) c.setRequestProperty("Authorization", "Bearer " + token);
        return c;
    }

    private static String readAll(InputStream in) throws IOException {
        if (in == null) return "";
        try (InputStream i = in) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            for (int r; (r = i.read(buf)) > 0; ) out.write(buf, 0, r);
            return out.toString("UTF-8");
        }
    }

    private static String errorText(String body) {
        try {
            return new JSONObject(body).optString("error", body);
        } catch (JSONException e) {
            return body;
        }
    }
}
