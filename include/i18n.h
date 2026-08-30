#pragma once

#include "esp_err.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// Languages – order must match locales/*.json generation (en=0, de=1)
typedef enum {
    LANG_EN = 0,
    LANG_DE = 1,
    LANG_COUNT = 2
} lang_t;

// NVS storage for language (1 byte)
#define NVS_I18N_NAMESPACE "i18n"
#define NVS_KEY_LANG "lang"

// Cached current lang, loaded at boot
lang_t i18n_load_lang(void);               // NVS -> LANG_* , default EN
esp_err_t i18n_set_lang(lang_t lang);      // NVS write + cache update
lang_t i18n_get_current(void);             // cached value (no NVS read)

// Translation lookup – fallback EN, never NULL
const char* i18n_get(lang_t lang, const char *key);

// Parse "en", "de", "de-DE" -> LANG_*, LANG_COUNT on invalid
lang_t i18n_parse_code(const char *code);

#ifdef __cplusplus
}
#endif
