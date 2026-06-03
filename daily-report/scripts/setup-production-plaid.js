#!/usr/bin/env node

/**
 * Interactive setup for Production/Development Plaid
 * Helps you link your real bank account
 */

const { Configuration, PlaidApi, PlaidEnvironments, Products, CountryCode } = require('plaid');
const readline = require('readline');
const fs = require('fs');

const CLIENT_ID = '6a1e7548b033d9000d7b75fd';

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function question(query) {
  return new Promise(resolve => rl.question(query, resolve));
}

async function setup() {
  console.log('🏦 Plaid Production/Development Setup\n');
  console.log('This will help you link your REAL bank account.\n');

  // Step 1: Get environment choice
  console.log('📋 Choose Environment:\n');
  console.log('1. Development (FREE, up to 100 accounts, real data)');
  console.log('2. Production (Requires approval, unlimited)\n');

  const envChoice = await question('Enter choice (1 or 2): ');
  const useDevelopment = envChoice.trim() === '1';
  const environment = useDevelopment ? 'development' : 'production';

  console.log(`\n✓ Selected: ${environment}\n`);

  // Step 2: Get secret
  console.log('🔑 Get your secret from Plaid Dashboard:\n');
  console.log('   1. Go to: https://dashboard.plaid.com/team/keys');
  console.log(`   2. Copy your ${environment.toUpperCase()} secret`);
  console.log(`   3. It should start with "${environment}-"\n`);

  const secret = await question('Enter your secret: ');

  if (!secret.startsWith(environment + '-')) {
    console.error(`\n❌ Error: Secret should start with "${environment}-"`);
    console.error('   Please get the correct secret from Plaid Dashboard.');
    rl.close();
    process.exit(1);
  }

  console.log('\n✓ Secret validated\n');

  try {
    // Step 3: Create link token
    const configuration = new Configuration({
      basePath: PlaidEnvironments[environment],
      baseOptions: {
        headers: {
          'PLAID-CLIENT-ID': CLIENT_ID,
          'PLAID-SECRET': secret,
        },
      },
    });

    const client = new PlaidApi(configuration);

    console.log('⏳ Creating Plaid Link token...');

    const linkResponse = await client.linkTokenCreate({
      user: {
        client_user_id: 'user-' + Date.now(),
      },
      client_name: 'OpenPaw Daily Digest',
      products: [Products.Transactions],
      country_codes: [CountryCode.Us],
      language: 'en',
    });

    const linkToken = linkResponse.data.link_token;
    console.log('✓ Link token created\n');

    // Step 4: Generate Plaid Link HTML
    const html = `<!DOCTYPE html>
<html>
<head>
  <title>Link Your Bank Account</title>
  <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      max-width: 600px;
      margin: 50px auto;
      padding: 20px;
      text-align: center;
    }
    button {
      background: #0066ff;
      color: white;
      border: none;
      padding: 15px 30px;
      font-size: 16px;
      border-radius: 8px;
      cursor: pointer;
      margin: 20px 0;
    }
    button:hover {
      background: #0052cc;
    }
    #result {
      margin-top: 20px;
      padding: 15px;
      background: #f5f5f5;
      border-radius: 8px;
      font-family: monospace;
      white-space: pre-wrap;
      word-break: break-all;
      display: none;
    }
    .success {
      background: #e6f7e6;
      border: 1px solid #4caf50;
    }
  </style>
</head>
<body>
  <h1>🏦 Link Your Bank Account</h1>
  <p>Click the button below to connect your bank account securely through Plaid.</p>

  <button id="linkButton">Connect Bank Account</button>

  <div id="result"></div>

  <script>
    const linkToken = '${linkToken}';

    const handler = Plaid.create({
      token: linkToken,
      onSuccess: (public_token, metadata) => {
        const resultDiv = document.getElementById('result');
        resultDiv.className = 'success';
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = \`✅ Success! Your bank is linked.

PUBLIC TOKEN (copy this):
\${public_token}

Institution: \${metadata.institution.name}

📋 Next Steps:
1. Copy the public token above
2. Run: node scripts/exchange-public-token.js
3. Paste the public token when prompted
4. You'll get your access token!\`;
      },
      onExit: (err, metadata) => {
        if (err) {
          alert('Error: ' + err);
        } else {
          console.log('User exited');
        }
      },
    });

    document.getElementById('linkButton').onclick = function() {
      handler.open();
    };
  </script>
</body>
</html>`;

    const htmlPath = '/tmp/plaid-link.html';
    fs.writeFileSync(htmlPath, html);

    console.log('🌐 Plaid Link page created!\n');
    console.log('📋 Next Steps:\n');
    console.log('1. Open this file in your browser:');
    console.log(`   ${htmlPath}\n`);
    console.log('2. Click "Connect Bank Account"');
    console.log('3. Log in to your bank');
    console.log('4. Copy the PUBLIC TOKEN from the page');
    console.log('5. Run: node scripts/exchange-public-token.js');
    console.log('6. Paste the public token\n');

    console.log('💡 Opening in your default browser...');

    // Try to open the file
    const { exec } = require('child_process');
    exec(`open ${htmlPath}`, (error) => {
      if (error) {
        console.log('\n⚠️  Could not auto-open. Please open manually:');
        console.log(`   ${htmlPath}`);
      }
    });

    console.log('\n⌨️  Press Enter when you have the public token...');
    await question('');

    console.log('\n🔄 Continue with: node scripts/exchange-public-token.js\n');

    rl.close();

  } catch (error) {
    console.error('\n❌ Error:', error.response?.data || error.message);
    rl.close();
    process.exit(1);
  }
}

setup();
