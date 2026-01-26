const fs = require('fs');
const path = require('path');
const JavaScriptObfuscator = require('javascript-obfuscator');

// Configuration: List files to obfuscate here
// Currently pointing to a placeholder. Once you extract JS from search.html to 'static/js/app.js', update this.
const FILES_TO_OBFUSCATE = [
    // './documents/static/documents/js/app.js' 
];

const OUTPUT_DIR = './documents/static/documents/js/dist';

// Ensure output directory exists
// if (!fs.existsSync(OUTPUT_DIR)){
//     fs.mkdirSync(OUTPUT_DIR, { recursive: true });
// }

console.log('Starting obfuscation...');

if (FILES_TO_OBFUSCATE.length === 0) {
    console.log('No files configured to obfuscate. Extract JS from HTML first.');
    console.log('See MIGRATION_DETAILS.md for instructions.');
}

FILES_TO_OBFUSCATE.forEach(filePath => {
    if (fs.existsSync(filePath)) {
        const fileContent = fs.readFileSync(filePath, 'utf8');

        const obfuscationResult = JavaScriptObfuscator.obfuscate(fileContent, {
            compact: true,
            controlFlowFlattening: true,
            controlFlowFlatteningThreshold: 1,
            numbersToExpressions: true,
            simplify: true,
            stringArrayShuffle: true,
            splitStrings: true,
            stringArrayThreshold: 1
        });

        const fileName = path.basename(filePath);
        const outputPath = path.join(OUTPUT_DIR, fileName);

        fs.writeFileSync(outputPath, obfuscationResult.getObfuscatedCode());
        console.log(`✓ Obfuscated: ${fileName}`);
    } else {
        console.log(`⚠ File not found: ${filePath}`);
    }
});
