# NPM Setup Instructions

## Current Status

The dependency `@richard-paredes-1/corp-style` has been removed from `package.json` because of authentication issues with GitHub Packages.

The file `documents/static/documents/vendor/corp-style.css` already exists in the repository, so the build should work without reinstalling the package.

## Steps to Run NPM

Simply run:
```powershell
cd "C:\Proyecto - búsqueda inteligente con minio"
npm install
npm test
```

No GitHub token is required anymore.

## If You Want to Re-add the GitHub Package

1. Create a GitHub personal access token (classic) with `read:packages` scope.
2. Set the environment variable:
   ```powershell
   $env:NPM_GITHUB_TOKEN = "ghp_your_token_here"
   ```
3. Add the dependency back to `package.json`:
   ```json
   "dependencies": {
       "@richard-paredes-1/corp-style": "1.2.3"
   }
   ```
4. Run `npm install`.

## Build Process

The `sync:corp-style` script copies the CSS from `node_modules` to `vendor`. Since the package is not installed, the script will skip syncing if `vendor/corp-style.css` already exists.

If you need to update the CSS, manually download the latest version or set up authentication as described above.

## Troubleshooting

- If `npm install` fails, check that your `.npmrc` doesn't have conflicting settings.
- The `.npmrc` file still contains the registry setting for `@richard-paredes-1`, but it won't be used since the dependency is removed.
