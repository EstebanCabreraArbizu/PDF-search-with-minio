const fs = require('fs');
const path = require('path');

const sourcePath = path.resolve(
  __dirname,
  '..',
  'node_modules',
  '@richard-paredes-1',
  'corp-style',
  'dist',
  'index.css'
);

const targetDir = path.resolve(
  __dirname,
  '..',
  'documents',
  'static',
  'documents',
  'vendor'
);

const targetPath = path.resolve(targetDir, 'corp-style.css');

if (!fs.existsSync(sourcePath)) {
  if (fs.existsSync(targetPath)) {
    console.warn('Corp style source not found, but target already exists. Skipping sync.');
    process.exit(0);
  } else {
    console.error('Corp style source not found at:', sourcePath);
    console.error('Run npm install with GitHub Packages credentials first.');
    process.exit(1);
  }
}

fs.mkdirSync(targetDir, { recursive: true });

// Django + WhiteNoise manifest parsing also scans CSS comments for url(...),
// so we sanitize bare package specifiers that are docs/examples, not assets.
let css = fs.readFileSync(sourcePath, 'utf8');
css = css.replace(/@import\s+url\((['"]@liderman\/corp-style\1\);?/g, '/* @import removed for Django static manifest */');
css = css.replace(/url\((['"]@liderman\/[\s\S]*?\1\)/g, 'url("https://example.invalid/")');

fs.writeFileSync(targetPath, css, 'utf8');

console.log('Synced corp style CSS to:', targetPath);
