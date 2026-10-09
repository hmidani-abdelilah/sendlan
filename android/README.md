# SendLan Android Build

This folder contains the Flet entry point and configuration for the Android app.

## Run the app locally

```bash
cd android
python -m flet run main.py
```

## Build the Android APK

Run the build command from the project root. The generated APK is written to
`android/build/`.

```bash
cd /home/xq/sendlan
flet build apk android -o android/build
```

The Android project pins `jni ^1.1.0` in `android/pyproject.toml` to keep the
generated Flutter app compatible with the JNI package.

## Run the desktop app

```bash
cd /home/xq/sendlan
python main.py
```