# Implementation Plan - Fix Build and Manifest Errors

The project is currently experiencing build failures and IDE errors (manifest attribute validation) due to an invalid `applicationId` configuration and a mismatch with `google-services.json`.

## User Review Required

> [!IMPORTANT]
> I will be changing the `applicationId` to `com.example.iknowu`. This is necessary to match the existing `google-services.json` and to remove invalid package segments (like `.26`).
> This change will resolve the following:
> 1. AAPT error regarding invalid package names.
> 2. Firebase error regarding missing client in `google-services.json`.
> 3. IDE manifest validation errors (`android:functionalTest` not allowed, etc.), which are side-effects of the invalid package name in the generated manifest.

## Proposed Changes

### Build Configuration

#### [MODIFY] [build.gradle.kts](file:///C:/Users/kjonh/AndroidStudioProjects/IKnowU/app/build.gradle.kts)
- Set `applicationId` to `com.example.iknowu`.
- Remove `applicationIdSuffix = "26"` from `defaultConfig`.
- Remove `applicationIdSuffix = "iknowu_dbg"` from the `debug` build type.
- Remove `applicationIdSuffix = "iknowu"` from the `release` build type.
- *Reasoning*: The `google-services.json` only contains a configuration for `com.example.iknowu`. Using suffixes creates IDs that don't match the Firebase config.

## Verification Plan

### Automated Tests
- Run `gradle_assemble_all` to verify the project builds successfully.
- Run `gradle_sync` to refresh IDE state and clear "Attribute not allowed" and "URI not registered" errors.

### Manual Verification
- Check the generated manifest for tests to ensure the `package` name is now valid.
