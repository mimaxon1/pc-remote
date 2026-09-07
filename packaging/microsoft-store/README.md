# Microsoft Store MSIX packaging

This is the zero-cost Store path for PC Remote.

Do not submit the existing Inno Setup EXE to Microsoft Store unless it has been Authenticode-signed with a certificate trusted by Microsoft. The Store does not re-sign EXE/MSI installers. For MSIX submissions, Microsoft re-signs the package after certification, so a paid CA-trusted certificate is not required for Store distribution.

## Before building

Create/reserve the app in Microsoft Partner Center and copy these three values exactly from the product identity page:

1. Package/Identity Name
2. Publisher
3. Publisher display name

Do not guess these values. Package identity is case-sensitive and a Store package must match the identity assigned by Partner Center.

The developer account must satisfy Microsoft's current eligibility and identity-verification requirements.

## Build locally

First build the normal PyInstaller directory:

```powershell
python build_release.py --reset-settings
```

Then build the unsigned Store MSIX:

```powershell
.\packaging\microsoft-store\build_msix.ps1 `
  -IdentityName '<Partner Center Package/Identity Name>' `
  -Publisher '<Partner Center Publisher>' `
  -PublisherDisplayName '<Partner Center publisher display name>' `
  -Version '1.5.0'
```

Output:

```text
release\store\PC-Remote-1.5.0-store-x64.msix
```

The helper:

- copies the existing PyInstaller bundle into an MSIX staging directory;
- generates required package logo sizes from `web/icons/icon-192.png`;
- renders `Package.appxmanifest.template` using Partner Center identity values;
- packs the folder using `MakeAppx.exe` from the installed Windows SDK;
- leaves the Store package unsigned on purpose.

For a Microsoft Store MSIX submission, Partner Center re-signs the package after certification. Do not add an untrusted/self-signed signature to the final Store artifact just to silence local install warnings.

## Build through GitHub Actions

Use the `Build Microsoft Store MSIX` workflow and enter the three Partner Center identity values plus the version. The workflow uploads the unsigned `.msix` as an artifact and does not publish it automatically.

## Required validation before submission

1. Build with the exact Partner Center identity values.
2. Test the app behavior from the packaged build, especially LAN access, QR pairing, tray behavior, settings persistence and autostart.
3. Run the Windows App Certification Kit against the final package.
4. Confirm the package version is higher than the previous Store version.
5. Complete the Partner Center submission fields and certification notes accurately.

## Listing requirements relevant to PC Remote

For a normal MSIX app listing, provide at least:

- app name/reserved product identity;
- category;
- pricing and availability (Free for PC Remote);
- age-rating questionnaire;
- description;
- at least one real screenshot (four or more recommended);
- applicable license terms;
- package/MSIX upload;
- any required declarations for capabilities used by the package.

A privacy-policy URL is required when an app collects or transmits personal information. PC Remote includes a public `PRIVACY.md` regardless, so it can be supplied in the listing.

Store-specific listing logos are optional for normal MSIX apps, but a 300 x 300 app tile icon is recommended. If no separate listing icon is uploaded, the Store can use the icon from the MSIX package.

Prepared English and Russian listing text is in this directory.

## Screenshot checklist

A screenshot is not generated automatically because the Store should show the real shipping UI, not a mockup. Before submission, capture at least:

- QR pairing/status window;
- phone browser main control screen;
- apps/windows screen;
- media/audio screen.

Remove PINs, tokens, private notifications, personal names and other sensitive information before capture.
