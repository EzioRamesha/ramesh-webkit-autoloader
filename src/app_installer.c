/*
 * PS5 Homescreen App Installer for the WebKit Autoloader Installer.
 * Based on the original implementation in ftpsrv by John Törnblom
 * and Payload Manager by PLK.
 *
 * Iris branding: icon0 + pic0/pic1 (home focus backdrop) + enriched param.
 * AppInstUtil often leaves appmeta incomplete on update — we uninstall the
 * existing tile first, then rewrite sce_sys + /user/appmeta after register.
 */

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "app_installer.h"
#include "wkali.h"
#include <ps5/kernel.h>

#define INCASSET(name, file)                                                   \
  __asm__(".section .rodata\n"                                                 \
          ".global " #name "\n"                                                \
          ".global " #name "_end\n"                                            \
          ".global " #name "_size\n"                                           \
          ".align 16\n" #name ":\n"                                            \
          ".incbin \"" file "\"\n" #name "_end:\n" #name "_size:\n"            \
          ".quad " #name "_end - " #name "\n"                                  \
          ".previous\n");                                                      \
  extern const uint8_t name[];                                                 \
  extern const size_t name##_size;

INCASSET(param_json, "assets/param.json");
INCASSET(icon0_png, "assets/icon0.png");
/* Shared backdrop bytes written as both pic0 (wiki "background") and pic1
 * (homebrew healers treat pic1 as full-bleed focus art). */
INCASSET(pic0_png, "assets/homescreen/pic0.png");

int sceAppInstUtilInitialize(void);
int sceAppInstUtilTerminate(void);
int sceAppInstUtilAppInstallAll(void *);
int sceAppInstUtilAppUnInstall(const char *);

_Static_assert(sizeof(WKAL_TITLE_ID) <= 16, "WKAL_TITLE_ID too long for path buffers");

static int install_file(const char *path, const uint8_t *data, size_t size) {
  FILE *f;
  if (!(f = fopen(path, "wb"))) {
    return -1;
  }
  if (fwrite(data, size, 1, f) != 1) {
    fclose(f);
    return -1;
  }
  fclose(f);
  return 0;
}

static int install_app(const char *title_id, const char *dir) {
  int (*sceAppInstUtilAppInstallTitleDir)(const char *, const char *, void *) =
      0;
  const char *nid = "Wudg3Xe3heE";
  uint32_t handle;

  if (!kernel_dynlib_handle(-1, "libSceAppInstUtil.sprx", &handle)) {
    sceAppInstUtilAppInstallTitleDir =
        (void *)kernel_dynlib_resolve(-1, handle, nid);
  }

  if (sceAppInstUtilAppInstallTitleDir) {
    return sceAppInstUtilAppInstallTitleDir(title_id, dir, 0);
  }

  return sceAppInstUtilAppInstallAll(0);
}

static int needs_update(const char *path, const uint8_t *expected_data,
                        size_t expected_size) {
  struct stat st;
  if (stat(path, &st) != 0)
    return 1;
  if ((size_t)st.st_size != expected_size)
    return 1;

  FILE *f = fopen(path, "rb");
  if (!f)
    return 1;

  uint8_t *buf = malloc(expected_size);
  if (!buf) {
    fclose(f);
    return 1;
  }

  if (fread(buf, 1, expected_size, f) != expected_size) {
    free(buf);
    fclose(f);
    return 1;
  }
  fclose(f);

  int mismatch = memcmp(buf, expected_data, expected_size);
  free(buf);

  return mismatch != 0;
}

/**
 * Write icon/param/pics into sce_sys for the title.
 * @return 0 on success, -1 on failure (caller terminates AppInstUtil).
 */
static int write_sce_sys(const char *title_id) {
  char param_path[256];
  char icon_path[256];
  char pic0_path[256];
  char pic1_path[256];
  char sce_sys_dir[256];
  char base_dir[256];

  snprintf(base_dir, sizeof(base_dir), "/user/app/%s", title_id);
  snprintf(sce_sys_dir, sizeof(sce_sys_dir), "/user/app/%s/sce_sys", title_id);
  snprintf(param_path, sizeof(param_path), "/user/app/%s/sce_sys/param.json",
           title_id);
  snprintf(icon_path, sizeof(icon_path), "/user/app/%s/sce_sys/icon0.png",
           title_id);
  snprintf(pic0_path, sizeof(pic0_path), "/user/app/%s/sce_sys/pic0.png",
           title_id);
  snprintf(pic1_path, sizeof(pic1_path), "/user/app/%s/sce_sys/pic1.png",
           title_id);

  if (mkdir(base_dir, 0755) && errno != EEXIST) {
    wkali_log("[WKALI] Failed to create app dir: %s (errno: %d)\n", base_dir,
              errno);
    return -1;
  }
  if (mkdir(sce_sys_dir, 0755) && errno != EEXIST) {
    wkali_log("[WKALI] Failed to create sce_sys dir: %s (errno: %d)\n",
              sce_sys_dir, errno);
    return -1;
  }

  if (install_file(param_path, param_json, param_json_size)) {
    wkali_log("[WKALI] Failed to install param.json\n");
    return -1;
  }
  if (install_file(icon_path, icon0_png, icon0_png_size)) {
    wkali_log("[WKALI] Failed to install icon0.png\n");
    return -1;
  }
  if (install_file(pic0_path, pic0_png, pic0_png_size)) {
    wkali_log("[WKALI] Failed to install pic0.png\n");
    return -1;
  }
  if (install_file(pic1_path, pic0_png, pic0_png_size)) {
    wkali_log("[WKALI] Failed to install pic1.png\n");
    return -1;
  }
  return 0;
}

/**
 * Mirror metadata into /user/appmeta/<title>/ — home UI reads focus art here.
 */
static void mirror_appmeta(const char *title_id) {
  char meta_dir[256];
  char path[256];

  snprintf(meta_dir, sizeof(meta_dir), "/user/appmeta/%s", title_id);
  if (mkdir(meta_dir, 0755) && errno != EEXIST) {
    wkali_log("[WKALI] appmeta mkdir failed: %s errno=%d\n", meta_dir, errno);
    return;
  }

  snprintf(path, sizeof(path), "/user/appmeta/%s/param.json", title_id);
  if (install_file(path, param_json, param_json_size))
    wkali_log("[WKALI] appmeta param.json failed\n");

  snprintf(path, sizeof(path), "/user/appmeta/%s/icon0.png", title_id);
  if (install_file(path, icon0_png, icon0_png_size))
    wkali_log("[WKALI] appmeta icon0.png failed\n");

  /* pic1 first — prosperismo/homebrew healers treat it as full-bleed backdrop. */
  snprintf(path, sizeof(path), "/user/appmeta/%s/pic1.png", title_id);
  if (install_file(path, pic0_png, pic0_png_size))
    wkali_log("[WKALI] appmeta pic1.png failed\n");

  snprintf(path, sizeof(path), "/user/appmeta/%s/pic0.png", title_id);
  if (install_file(path, pic0_png, pic0_png_size))
    wkali_log("[WKALI] appmeta pic0.png failed\n");
}

int wkali_install_app_if_needed(void) {
  const char *title_id = WKAL_TITLE_ID;
  char base_dir[256];
  char param_path[256];
  char icon_path[256];
  char pic0_path[256];
  char pic1_path[256];
  char meta_pic1[256];

  snprintf(base_dir, sizeof(base_dir), "/user/app/%s", title_id);
  snprintf(param_path, sizeof(param_path), "/user/app/%s/sce_sys/param.json",
           title_id);
  snprintf(icon_path, sizeof(icon_path), "/user/app/%s/sce_sys/icon0.png",
           title_id);
  snprintf(pic0_path, sizeof(pic0_path), "/user/app/%s/sce_sys/pic0.png",
           title_id);
  snprintf(pic1_path, sizeof(pic1_path), "/user/app/%s/sce_sys/pic1.png",
           title_id);
  snprintf(meta_pic1, sizeof(meta_pic1), "/user/appmeta/%s/pic1.png", title_id);

  int update_needed = 0;
  struct stat st;
  if (stat(base_dir, &st) != 0) {
    update_needed = 1;
  } else {
    if (needs_update(param_path, param_json, param_json_size))
      update_needed = 1;
    if (needs_update(icon_path, icon0_png, icon0_png_size))
      update_needed = 1;
    if (needs_update(pic0_path, pic0_png, pic0_png_size))
      update_needed = 1;
    if (needs_update(pic1_path, pic0_png, pic0_png_size))
      update_needed = 1;
    /* Also refresh when appmeta backdrop is missing (hollow registration). */
    if (needs_update(meta_pic1, pic0_png, pic0_png_size))
      update_needed = 1;
  }

  if (!update_needed) {
    return 0;
  }

  if (stat(base_dir, &st) == 0) {
    wkali_log("[WKALI] Updating Iris launcher (%s)...\n", title_id);
    wkali_notify("Updating Iris...");
  } else {
    wkali_log("[WKALI] Installing Iris launcher (%s)...\n", title_id);
    wkali_notify("Installing Iris...");
  }

  int err;
  if ((err = sceAppInstUtilInitialize())) {
    wkali_log("[WKALI] sceAppInstUtilInitialize: error 0x%08X\n", err);
    return -1;
  }

  /* Fresh registration so AppInstUtil rebuilds appmeta from sce_sys. */
  err = sceAppInstUtilAppUnInstall(title_id);
  if (err)
    wkali_log("[WKALI] %s uninstall before reinstall: 0x%08X (ok if missing)\n",
              title_id, err);
  else
    wkali_log("[WKALI] Removed existing %s for clean theme reinstall\n",
              title_id);

  if (strcmp(title_id, WKAL_LEGACY_TITLE_ID) != 0) {
    int uerr = sceAppInstUtilAppUnInstall(WKAL_LEGACY_TITLE_ID);
    if (uerr)
      wkali_log("[WKALI] Legacy %s uninstall: 0x%08X (ok if missing)\n",
                WKAL_LEGACY_TITLE_ID, uerr);
    else
      wkali_log("[WKALI] Removed legacy Media tile %s\n", WKAL_LEGACY_TITLE_ID);
  }

  if (write_sce_sys(title_id)) {
    sceAppInstUtilTerminate();
    return -1;
  }

  if ((err = install_app(title_id, "/user/app/"))) {
    wkali_log("[WKALI] install_app: error 0x%08X\n", err);
    sceAppInstUtilTerminate();
    return -1;
  }

  /* install_app can rewrite/clear sce_sys — put art back, then mirror appmeta. */
  if (write_sce_sys(title_id))
    wkali_log("[WKALI] post-register sce_sys rewrite had errors\n");
  mirror_appmeta(title_id);

  wkali_log("[WKALI] Iris launcher installed successfully.\n");
  wkali_notify("Iris Ready — reboot once");

  sceAppInstUtilTerminate();
  return 0;
}
