#include "i18n.h"
#include "i18n_keys.h"
#include "i18n_data.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_log.h"
#include <string.h>
#include <strings.h>

static const char *TAG = "i18n";

static volatile lang_t s_current_lang = LANG_EN;
static volatile bool s_current_valid = false;

// Fallback strings if something goes very wrong
static const char *empty_str = "";

lang_t i18n_parse_code(const char *code) {
    if (!code || !code[0]) return LANG_COUNT;
    // allow "de", "de-DE", "DE", etc.
    if (strncasecmp(code, "de", 2) == 0) return LANG_DE;
    if (strncasecmp(code, "en", 2) == 0) return LANG_EN;
    return LANG_COUNT;
}

lang_t i18n_load_lang(void) {
    if (s_current_valid) return s_current_lang;
    nvs_handle_t h;
    if (nvs_open(NVS_I18N_NAMESPACE, NVS_READONLY, &h) != ESP_OK) {
        s_current_lang = LANG_EN;
        s_current_valid = true;
        return s_current_lang;
    }
    uint8_t v = 0;
    esp_err_t err = nvs_get_u8(h, NVS_KEY_LANG, &v);
    nvs_close(h);
    if (err == ESP_OK && v < LANG_COUNT) {
        s_current_lang = (lang_t)v;
    } else {
        s_current_lang = LANG_EN;
    }
    s_current_valid = true;
    ESP_LOGI(TAG, "Loaded lang: %s (%d)", I18N_LANG_CODES[s_current_lang], s_current_lang);
    return s_current_lang;
}

esp_err_t i18n_set_lang(lang_t lang) {
    if (lang >= LANG_COUNT) return ESP_ERR_INVALID_ARG;
    nvs_handle_t h;
    esp_err_t err = nvs_open(NVS_I18N_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_open failed: %s", esp_err_to_name(err));
        return err;
    }
    err = nvs_set_u8(h, NVS_KEY_LANG, (uint8_t)lang);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    if (err == ESP_OK) {
        s_current_lang = lang;
        s_current_valid = true;
        ESP_LOGI(TAG, "Saved lang: %s", I18N_LANG_CODES[lang]);
    } else {
        ESP_LOGE(TAG, "Failed to save lang: %s", esp_err_to_name(err));
    }
    return err;
}

lang_t i18n_get_current(void) {
    if (s_current_valid) return s_current_lang;
    return i18n_load_lang();
}

// Binary search – I18N_KEYS is sorted alphabetically by generator
const char* i18n_get(lang_t lang, const char *key) {
    if (!key) return empty_str;
    if (lang >= LANG_COUNT) lang = LANG_EN;
    int lo = 0, hi = I18N_KEY_COUNT - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        int cmp = strcmp(key, I18N_KEYS[mid]);
        if (cmp == 0) {
            const char *v = I18N_TABLE[lang][mid];
            if (v && v[0]) return v;
            // fallback EN
            return I18N_TABLE[LANG_EN][mid];
        } else if (cmp < 0) {
            hi = mid - 1;
        } else {
            lo = mid + 1;
        }
    }
    ESP_LOGW(TAG, "missing key: %s", key);
    return key; // fallback: return key itself to avoid empty UI
}
