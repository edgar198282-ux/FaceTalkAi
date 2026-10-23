package ai.abaj.tv.home;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

public final class MainActivity extends Activity {
    private static final String TV_PACKAGE = "ai.abaj.tv.standalone";
    private static final String PREF_AUTO = "auto_open_tv";
    private static final String PREF_BOOT = "last_boot";
    private static final int BACKGROUND = Color.rgb(8, 17, 31);
    private static final int ACCENT = Color.rgb(32, 224, 208);
    private static final int WHITE = Color.rgb(242, 248, 252);
    private static final int MUTED = Color.rgb(165, 189, 205);
    private static final int BUTTON_BG = Color.rgb(23, 48, 65);

    private final SharedPreferencesHolder preferences = new SharedPreferencesHolder();
    private boolean detailsVisible;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().getDecorView().setBackgroundColor(BACKGROUND);
        showHome();
        if (savedInstanceState == null) maybeOpenTVOnFirstHomeAfterBoot();
    }

    private final class SharedPreferencesHolder {
        SharedPreferences get() {
            return getSharedPreferences("abaj_tv_home", MODE_PRIVATE);
        }
    }

    private LinearLayout createRoot() {
        ScrollView scroller = new ScrollView(this);
        scroller.setFillViewport(true);
        scroller.setBackgroundColor(BACKGROUND);
        scroller.setVerticalScrollBarEnabled(false);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(dp(24), dp(20), dp(24), dp(20));
        scroller.addView(root, new ScrollView.LayoutParams(-1, -1));
        setContentView(scroller);
        return root;
    }

    private void showHome() {
        detailsVisible = false;
        LinearLayout root = createRoot();
        addTitle(root, "ABAJ TV", 43, ACCENT, true);
        addCaption(root, "IPTV  •  Кино  •  Медиа", 18, WHITE, 25);
        TextView open = addButton(root, "Открыть ABAJ TV", this::startTV);
        addButton(root, "Настройки Wi-Fi", () -> startSettings(Settings.ACTION_WIFI_SETTINGS));
        addButton(root, "Настройки Android", () -> startSettings(Settings.ACTION_SETTINGS));
        addButton(root, "Информация о приставке", this::showDeviceInfo);

        boolean auto = preferences.get().getBoolean(PREF_AUTO, true);
        TextView autoButton = addButton(root, autoLabel(auto), null);
        autoButton.setOnClickListener(v -> {
            boolean next = !preferences.get().getBoolean(PREF_AUTO, true);
            preferences.get().edit().putBoolean(PREF_AUTO, next).apply();
            autoButton.setText(autoLabel(next));
            Toast.makeText(this,
                    next ? "Автозапуск включён" : "Автозапуск выключен",
                    Toast.LENGTH_SHORT).show();
        });
        addCaption(root, "Работает поверх Android. Система МТС не изменяется.", 13, MUTED, 0);
        open.requestFocus();
    }

    private String autoLabel(boolean enabled) {
        return "Автозапуск после включения: " + (enabled ? "ВКЛ" : "ВЫКЛ");
    }

    private void showDeviceInfo() {
        detailsVisible = true;
        LinearLayout root = createRoot();
        addTitle(root, "ABAJ TV OS", 30, ACCENT, true);
        addCaption(root, "Диагностика (только чтение)", 16, WHITE, 15);
        addInfo(root, "Производитель", Build.MANUFACTURER);
        addInfo(root, "Модель", Build.MODEL);
        addInfo(root, "Устройство", Build.DEVICE);
        addInfo(root, "Плата", Build.BOARD);
        addInfo(root, "Аппаратная платформа", Build.HARDWARE);
        addInfo(root, "Загрузчик", Build.BOOTLOADER);
        addInfo(root, "Android", Build.VERSION.RELEASE + " (API " + Build.VERSION.SDK_INT + ")");
        addInfo(root, "Номер сборки", Build.DISPLAY);
        addInfo(root, "Сборка ОС", Build.VERSION.INCREMENTAL);
        addInfo(root, "Патч безопасности", Build.VERSION.SECURITY_PATCH);
        addInfo(root, "ABI", Build.SUPPORTED_ABIS.length > 0 ? Build.SUPPORTED_ABIS[0] : "неизвестно");
        addCaption(root, "Прошивки OTT и B866V2 несовместимы с B866 IPTV.", 15, MUTED, 10);
        TextView back = addButton(root, "Назад к ABAJ TV", this::showHome);
        back.requestFocus();
    }

    private void addInfo(LinearLayout root, String label, String value) {
        TextView field = new TextView(this);
        field.setText(label + ": " + ((value == null || value.trim().isEmpty()) ? "нет данных" : value));
        field.setTextColor(WHITE);
        field.setTextSize(16);
        field.setPadding(dp(7), dp(4), dp(7), dp(4));
        root.addView(field, new LinearLayout.LayoutParams(-1, -2));
    }

    private void addTitle(LinearLayout root, String text, int size, int color, boolean bold) {
        TextView title = new TextView(this);
        title.setText(text);
        title.setTextSize(size);
        if (bold) title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        title.setTextColor(color);
        title.setGravity(Gravity.CENTER);
        root.addView(title, new LinearLayout.LayoutParams(-1, -2));
    }

    private void addCaption(LinearLayout root, String text, int size, int color, int bottomMargin) {
        TextView caption = new TextView(this);
        caption.setText(text);
        caption.setTextColor(color);
        caption.setTextSize(size);
        caption.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.bottomMargin = dp(bottomMargin);
        params.topMargin = dp(6);
        root.addView(caption, params);
    }

    private TextView addButton(LinearLayout root, String label, Runnable action) {
        TextView button = new TextView(this);
        button.setText(label);
        button.setTextSize(19);
        button.setTextColor(WHITE);
        button.setGravity(Gravity.CENTER);
        button.setMinHeight(dp(55));
        button.setPadding(dp(20), dp(12), dp(20), dp(12));
        button.setBackground(buttonBackground(false));
        button.setFocusable(true);
        button.setClickable(true);
        if (action != null) button.setOnClickListener(v -> action.run());
        button.setOnFocusChangeListener((v, focused) -> {
            button.setBackground(buttonBackground(focused));
            button.setTextColor(focused ? BACKGROUND : WHITE);
        });
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                Math.max(dp(170), Math.min(dp(520),
                        getResources().getDisplayMetrics().widthPixels - dp(48))), -2);
        params.bottomMargin = dp(10);
        root.addView(button, params);
        return button;
    }

    private GradientDrawable buttonBackground(boolean focused) {
        GradientDrawable background = new GradientDrawable();
        background.setCornerRadius(dp(14));
        background.setColor(focused ? ACCENT : BUTTON_BG);
        return background;
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
        if (!preferences.get().getBoolean(PREF_AUTO, true)) return;
        int bootCount;
        try {
            bootCount = Settings.Global.getInt(getContentResolver(), Settings.Global.BOOT_COUNT, -1);
        } catch (SecurityException e) {
            return;
        }
        if (bootCount < 0 || preferences.get().getInt(PREF_BOOT, -1) == bootCount) return;
        preferences.get().edit().putInt(PREF_BOOT, bootCount).apply();
        startTV();
    }

    @Override
    public void onBackPressed() {
        if (detailsVisible) {
            showHome();
        } else {
            super.onBackPressed();
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
