# Credentials

Drop the Google Cloud service account JSON here as `service-account.json`.

The full path will then be:

```
.credentials/service-account.json
```

This directory is gitignored — credentials placed here cannot be committed.

The app auto-detects this file. If you'd rather use a different path, set
`GOOGLE_APPLICATION_CREDENTIALS` to point at the file before launching the
app.
