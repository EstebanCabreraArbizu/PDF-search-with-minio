const fs = require('fs');
const path = require('path');
const JavaScriptObfuscator = require('javascript-obfuscator');

const JS_ROOT = './documents/static/documents/js';
const OUTPUT_DIR = path.join(JS_ROOT, 'dist');

// Configuration for the obfuscator
const OBFUSCATOR_CONFIG = {
    compact: true,
    controlFlowFlattening: true,
    controlFlowFlatteningThreshold: 0.75,
    numbersToExpressions: true,
    simplify: true,
    stringArrayShuffle: true,
    splitStrings: true,
    stringArrayThreshold: 0.75,
    deadCodeInjection: true,
    deadCodeInjectionThreshold: 0.4,
    sourceMap: true,
    sourceMapMode: 'separate',
    reservedNames: ['DocSearchCore', 'DocSearchShared', 'state', 'results', 'count', 'init', 'search', 'renderResults', 'renderPagination', 'isLoading', 'metadata']
};

/**
 * Recursively gets all .js files in a directory, excluding the 'dist' folder.
 * @param {string} dirPath 
 * @param {string[]} arrayOfFiles 
 * @returns {string[]}
 */
const getAllJSFiles = (dirPath, arrayOfFiles = []) => {
    const files = fs.readdirSync(dirPath);

    files.forEach(file => {
        const fullPath = path.join(dirPath, file);
        if (fs.statSync(fullPath).isDirectory()) {
            // Skip the dist output directory
            if (file !== 'dist') {
                getAllJSFiles(fullPath, arrayOfFiles);
            }
        } else if (file.endsWith('.js')) {
            arrayOfFiles.push(fullPath);
        }
    });

    return arrayOfFiles;
};

// Ensure output directory exists
if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

console.log('--- JAVASCRIPT OBFUSCATION TOOL ---');
console.log(`Scanning directory: ${JS_ROOT}`);

const filesToObfuscate = getAllJSFiles(JS_ROOT);

if (filesToObfuscate.length === 0) {
    console.log('⚠ No .js files found to obfuscate.');
    process.exit(0);
}

console.log(`Found ${filesToObfuscate.length} files. Starting obfuscation...\n`);

filesToObfuscate.forEach(filePath => {
    const fileContent = fs.readFileSync(filePath, 'utf8');
    const relativePath = path.relative(JS_ROOT, filePath);
    
    // We'll flatten the output for now or we could reproduce the directory structure
    // Let's reproduce the structure in dist/ just in case
    const outputPath = path.join(OUTPUT_DIR, relativePath);
    const outputDir = path.dirname(outputPath);

    if (!fs.existsSync(outputDir)) {
        fs.mkdirSync(outputDir, { recursive: true });
    }

    try {
        const obfuscationResult = JavaScriptObfuscator.obfuscate(fileContent, OBFUSCATOR_CONFIG);
        fs.writeFileSync(outputPath, obfuscationResult.getObfuscatedCode());
        
        // Write source map if available
        const sourceMap = obfuscationResult.getSourceMap();
        if (sourceMap) {
            const sourceMapPath = outputPath + '.map';
            fs.writeFileSync(sourceMapPath, sourceMap);
            console.log(`  └─ Source map: ${path.relative(JS_ROOT, sourceMapPath)}`);
        }
        
        console.log(`✓ [OK] ${relativePath}`);
    } catch (err) {
        console.error(`✗ [ERROR] Failed to obfuscate ${relativePath}:`, err.message);
    }
});

console.log('\n--- OBFUSCATION COMPLETE ---');
console.log(`Files are available in: ${OUTPUT_DIR}`);
