# Vepol Desktop local shell

Build with `./desktop/build.sh` from the Face directory. The script scopes `DEVELOPER_DIR` to the existing standalone Command Line Tools before invoking the system make shim as well as the compiler. Selected Xcode, its license and global settings are not changed.

The output is `desktop/build/VepolDesktop.app`, ad-hoc signed for local use. The build records the current backend checkout in a generated bundle resource. The app uses that checkout's `.venv/bin/python -m vepol_face.desktop_server`; moving/removing the checkout requires rebuilding. Python is not bundled. This is not a distributable release.

Launch normally to own the backend at port 8781. A foreign listener is an error with Retry; production never tries another port. Cmd-W closes only the window. Cmd-R reloads with a fresh document-start token injection. Cmd-Q asks the backend whether work is in flight, preserves busy sessions, and waits for an idle backend to exit naturally.

For isolated native acceptance, pass `--test-config /absolute/path/to/config.json` through the app launch arguments. The JSON contains `port`, a required separate `state_dir`, and optional `hub`. It must not contain a token. The shell always generates its token in memory and sends it only through the inherited stdin pipe. The webview and shell HTTP client use nonpersistent stores.

The shell was compiled and signed locally. Launch, permission notification, runtime continuation, native board interactions and shutdown evidence belong to the integrated application acceptance. The shell itself provides no runtime transport or terminal takeover implementation.
