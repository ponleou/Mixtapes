/*
 * Mixtapes Windows Launcher
 * Minimal .exe that sets up the environment and launches the Python app.
 * Compiled with: windres launcher.rc -o launcher_res.o
 *                gcc -mwindows -o Mixtapes.exe launcher.c launcher_res.o
 */

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nCmdShow) {
    char exePath[MAX_PATH];
    char baseDir[MAX_PATH];
    char envBuf[4096];

    /* Get directory of this .exe */
    GetModuleFileNameA(NULL, exePath, MAX_PATH);
    char *lastSlash = strrchr(exePath, '\\');
    if (lastSlash) {
        *lastSlash = '\0';
        strcpy(baseDir, exePath);
    } else {
        strcpy(baseDir, ".");
    }

    /* Set environment variables */
    snprintf(envBuf, sizeof(envBuf), "%s\\runtime\\bin;%s", baseDir, getenv("PATH") ? getenv("PATH") : "");
    SetEnvironmentVariableA("PATH", envBuf);

    snprintf(envBuf, sizeof(envBuf), "%s\\runtime", baseDir);
    SetEnvironmentVariableA("PYTHONHOME", envBuf);

    snprintf(envBuf, sizeof(envBuf), "%s\\src", baseDir);
    SetEnvironmentVariableA("PYTHONPATH", envBuf);

    snprintf(envBuf, sizeof(envBuf), "%s\\runtime\\lib\\girepository-1.0", baseDir);
    SetEnvironmentVariableA("GI_TYPELIB_PATH", envBuf);

    snprintf(envBuf, sizeof(envBuf), "%s\\runtime\\lib\\gstreamer-1.0", baseDir);
    SetEnvironmentVariableA("GST_PLUGIN_PATH", envBuf);

    snprintf(envBuf, sizeof(envBuf), "%s\\runtime\\lib\\gio\\modules", baseDir);
    SetEnvironmentVariableA("GIO_MODULE_DIR", envBuf);

    snprintf(envBuf, sizeof(envBuf), "%s\\runtime\\share\\glib-2.0\\schemas", baseDir);
    SetEnvironmentVariableA("GSETTINGS_SCHEMA_DIR", envBuf);

    snprintf(envBuf, sizeof(envBuf), "%s\\runtime\\ssl\\certs\\ca-bundle.crt", baseDir);
    SetEnvironmentVariableA("SSL_CERT_FILE", envBuf);

    snprintf(envBuf, sizeof(envBuf), "%s\\runtime\\share", baseDir);
    SetEnvironmentVariableA("XDG_DATA_DIRS", envBuf);

    /* Build command: pythonw.exe (no console window) */
    char cmdLine[4096];
    snprintf(cmdLine, sizeof(cmdLine),
             "\"%s\\runtime\\bin\\pythonw.exe\" \"%s\\src\\main.py\"",
             baseDir, baseDir);

    /* Launch Python */
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessA(NULL, cmdLine, NULL, NULL, FALSE, 0, NULL, baseDir, &si, &pi)) {
        /* Fallback: try python3.exe if pythonw.exe doesn't exist */
        snprintf(cmdLine, sizeof(cmdLine),
                 "\"%s\\runtime\\bin\\python3.exe\" \"%s\\src\\main.py\"",
                 baseDir, baseDir);
        if (!CreateProcessA(NULL, cmdLine, NULL, NULL, FALSE, 0, NULL, baseDir, &si, &pi)) {
            MessageBoxA(NULL, "Failed to start Mixtapes.\n\n"
                        "Ensure the runtime directory is intact.",
                        "Mixtapes", MB_ICONERROR);
            return 1;
        }
    }

    /* Don't wait — let the app run independently */
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

    return 0;
}
