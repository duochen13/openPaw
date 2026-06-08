/**
 * Quick test script for PDF parsing
 */

const path = require('path');
const os = require('os');

async function testPdfParsing() {
  try {
    const { parsePdfReceipts } = require('./src/fetchers/pdfParser');

    const pdfFolder = path.join(os.homedir(), 'Downloads', 'uber-receipts');
    console.log('📁 Looking for PDFs in:', pdfFolder);
    console.log('');

    const results = await parsePdfReceipts(pdfFolder);

    console.log('✅ Parsed PDFs:', results.length);
    console.log('');

    results.forEach((receipt, index) => {
      console.log(`📄 PDF ${index + 1}:`);
      console.log('  Platform:', receipt.platform);
      console.log('  Restaurant:', receipt.restaurant);
      console.log('  Total:', receipt.total ? `$${receipt.total.toFixed(2)}` : 'N/A');
      console.log('  Items:', receipt.items.length);

      if (receipt.items.length > 0) {
        console.log('  Items details:');
        receipt.items.forEach(item => {
          console.log(`    - ${item.name} x${item.quantity} = $${item.price.toFixed(2)}`);
        });
      }

      console.log('  File:', receipt.filename);
      console.log('');
    });

    if (results.length === 0) {
      console.log('❌ No PDFs parsed successfully');
      console.log('');
      console.log('Troubleshooting:');
      console.log('1. Check if PDFs are in the folder');
      console.log('2. Check if pdf-parse package is installed');
      console.log('3. Check PDF content format');
    }

  } catch (error) {
    console.error('❌ Error:', error.message);
    console.error('Stack:', error.stack);
  }
}

testPdfParsing();
