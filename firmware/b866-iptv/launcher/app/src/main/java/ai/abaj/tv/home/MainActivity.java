package ai.abaj.tv.home;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

public final class MainActivity extends Activity {
    private static final String TV_PACKAGE = "ai.abaj.tv.standalone";
    private static final int BACKGROUND = Color.rgb(8, 17, 31);
    private static final int ACCENT = Color.rgb(32, 224, 208);
    private static final int WHITE = Color.rgb(242, 248, 252);

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().getDecorView().setBackgroundColor(BACKGROUND);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(dp(36), dp(28), dp(36), dp(28));
        setContentView(root);

        TextView title = new TextView(this);
        title.setText("ABAJ TV");
        title.setTextSize(43);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        title.setTextColor(ACCENT);
        title.setGravity(Gravity.CENTER);
        root.addView(title, new LinearLayout.LayoutParams(-1, -2));

        TextView subtitle = new TextView(this);
        subtitle.setText("TV  •  Кино  •  Медиа");
        subtitle.setTextColor(WHITE);
        subtitle.setTextSize(18);
        subtitle.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams subtitleParams = new LinearLayout.LayoutParams(-1, -2);
        subtitleParams.bottomMargin = dp(26);
        root.addView(subtitle, subtitleParams);

        addButton(root, "Открыть ABAJ TV", this::startTV, true);
        addButton(root, "Настройки Wi-Fi", () -> startSettings(Settings.ACTION_WIFI_SETTINGS), false);
        addButton(root, "Настройки Android", () -> startSettings(Settings.ACTION_SETTINGS), false);

        if (savedInstanceState == null) {
            maybeOpenTVOnFirstHomeAfterBoot();
        }
    }

    private void addButton(LinearLayout root, String text, Runnable action, boolean initialFocus) {
        TextView button = new TextView(this);
        button.setText(text);
        button.setTextSize(21);
        button.setTextColor(WHITE);
        button.setGravity(Gravity.CENTER);
        button.setPadding(dp(24), dp(17), dp(24), dp(17));
        button.setBackgroundColor(Color.rgb(23, 48, 65));
        button.setFocusable(true);
        button.setClickable(true);
        button.setOnClickListener(v -> action.run());
        button.setOnFocusChangeListener((v, focused) -> {
            button.setBackgroundColor(focused ? ACCENT : Color.rgb(23, 48, 65));
            button.setTextColor(focused ? BACKGROUND : WHITE);
        });
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                Math.min(dp(560), getResources().getDisplayMetrics().widthPixels - dp(72)),
                ViewGroup.LayoutParams.WRAP_CONTENT);
        params.bottomMargin = dp(12);
        root.addView(button, params);
        if (initialFocus) button.requestFocus();
    }

    private boolean startTV() {
        Intent launch = getPackageManager().getLeanbackLaunchIntentForPackage(TV_PACKAGE);
        if (launch == null) launch = getPackageManager().getLaunchIntentForPackage(TV_PACKAGE);
        if (launch == null) {
            Toast.makeText(this, "Установите ABAJ TV Standalone", Toast.LENGTH_LONG).show();
            return false;
        }
        try {
            startActivity(launch);
            return true;
        } catch (ActivityNotFoundException | SecurityException e) {
            Toast.makeText(this, "Не удалось открыть ABAJ TV", Toast.LENGTH_LONG).show();
            return false;
        }
    }

    private void startSettings(String action) {
        try {
            startActivity(new Intent(action));
        } catch (ActivityNotFoundException | SecurityException e) {
            Toast.makeText(this, "Настройка недоступна на этой приставке", Toast.LENGTH_SHORT).show();
        }
    }

    private void maybeOpenTVOnFirstHomeAfterBoot() {
        int bootCount;
        try {
            bootCount = Settings.Global.getInt(getContentResolver(), Settings.Global.BOOT_COUNT, -1);
        } catch (SecurityException e) {
            return;
        }
        if (bootCount < 0) return;
        SharedPreferences pref = getSharedPreferences("home", MODE_PRIVATE);
        if (pref.getInt("last_boot", -1) == bootCount) return;
        if (startTV()) pref.edit().putInt("last_boot", bootCount).apply();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
