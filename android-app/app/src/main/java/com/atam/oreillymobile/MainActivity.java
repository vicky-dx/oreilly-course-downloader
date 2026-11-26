package com.atam.oreillymobile;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.Context;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.graphics.Typeface;
import java.net.URL;

public class MainActivity extends Activity {
    private EditText urlInput;
    private TextView status;
    private LinearLayout root;
    private DownloadManager manager;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        manager = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
        ScrollView scroll = new ScrollView(this);
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(32, 40, 32, 32);
        root.setBackgroundColor(0xFF101713);
        scroll.addView(root);

        TextView title = new TextView(this);
        title.setText("O'REILLY MOBILE"); title.setTextSize(25); title.setTypeface(null, Typeface.BOLD);
        title.setTextColor(0xFFB7F77A); root.addView(title);
        TextView intro = new TextView(this);
        intro.setText("Standalone Android download manager\\nDownload direct files you are authorized to save (for example, your own MP4 or EPUB links).\\n");
        intro.setTextColor(0xFFE3EAE5); intro.setTextSize(15); intro.setPadding(0,18,0,18); root.addView(intro);

        urlInput = new EditText(this);
        urlInput.setSingleLine(true); urlInput.setHint("https://example.com/file.epub");
        urlInput.setHintTextColor(0xFF89958C); urlInput.setTextColor(0xFFFFFFFF);
        urlInput.setLinkTextColor(0xFFB7F77A); urlInput.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xFFB7F77A));
        root.addView(urlInput);

        Button download = new Button(this); download.setText("DOWNLOAD FILE");
        download.setOnClickListener(v -> startDownload()); root.addView(download);
        Button refresh = new Button(this); refresh.setText("REFRESH DOWNLOAD STATUS");
        refresh.setOnClickListener(v -> showRecent()); root.addView(refresh);

        status = new TextView(this); status.setTextColor(0xFFE3EAE5); status.setTextSize(14);
        status.setPadding(0,22,0,0); root.addView(status);
        TextView note = new TextView(this);
        note.setText("\\nNote: This app downloads ordinary direct file URLs. It does not sign in to O'Reilly, scrape protected course streams, bypass DRM, or defeat subscription/access controls. For O'Reilly materials, use official download/export options where available.");
        note.setTextColor(0xFFADB9B0); note.setTextSize(12); note.setPadding(0,24,0,0); root.addView(note);
        setContentView(scroll);
    }

    private void startDownload() {
        String value = urlInput.getText().toString().trim();
        try {
            URL url = new URL(value);
            if (!"https".equalsIgnoreCase(url.getProtocol()) && !"http".equalsIgnoreCase(url.getProtocol())) throw new IllegalArgumentException("Only HTTP/HTTPS URLs are supported.");
            String name = url.getPath();
            name = name.substring(name.lastIndexOf('/') + 1);
            if (name.isEmpty()) name = "download-" + System.currentTimeMillis();
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(value));
            request.setTitle(name);
            request.setDescription("O'Reilly Mobile download");
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, "OReillyMobile/" + name);
            long id = manager.enqueue(request);
            status.setText("Download queued. Android will show progress in notifications.\\nDownload ID: " + id + "\\nSaved under Downloads/OReillyMobile/");
        } catch (Exception e) {
            status.setText("Could not start download: " + e.getMessage());
        }
    }

    private void showRecent() {
        DownloadManager.Query query = new DownloadManager.Query();
        try (android.database.Cursor cursor = manager.query(query)) {
            StringBuilder out = new StringBuilder("Recent downloads:\\n");
            if (cursor != null && cursor.moveToFirst()) {
                do {
                    int titleCol = cursor.getColumnIndex(DownloadManager.COLUMN_TITLE);
                    int statusCol = cursor.getColumnIndex(DownloadManager.COLUMN_STATUS);
                    String name = titleCol >= 0 ? cursor.getString(titleCol) : "File";
                    int s = statusCol >= 0 ? cursor.getInt(statusCol) : -1;
                    String state = s == DownloadManager.STATUS_SUCCESSFUL ? "Complete" : s == DownloadManager.STATUS_FAILED ? "Failed" : s == DownloadManager.STATUS_RUNNING ? "Downloading" : s == DownloadManager.STATUS_PENDING ? "Queued" : "In progress";
                    out.append("• ").append(name).append(" — ").append(state).append("\\n");
                } while (cursor.moveToNext());
            } else out.append("No downloads found.");
            status.setText(out.toString());
        }
    }
}
