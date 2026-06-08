# Enable Uber Eats Itemization - Network Issue Detected

## 🚨 Current Problem

Your system **cannot reach npm registry** due to DNS resolution failure:

```bash
$ ping registry.npmjs.org
ping: cannot resolve registry.npmjs.org: Unknown host
```

This is why `npm install pdf-parse` keeps failing with:
```
npm error ENOTFOUND registry.npmjs.org
```

## 🔍 What's Causing This

**DNS Resolution Failure** - Your computer cannot resolve the domain name `registry.npmjs.org` to an IP address. This could be due to:

1. **Network connectivity issues** - WiFi/Ethernet disconnected or unstable
2. **DNS server problems** - Your configured DNS servers aren't responding
3. **VPN/Proxy issues** - VPN or corporate proxy blocking npm registry
4. **Firewall rules** - Firewall blocking DNS or npm traffic
5. **Hosts file override** - `/etc/hosts` file blocking npm registry (less likely)

## ✅ How to Fix

### Step 1: Check Your Network Connection

```bash
# Check if you're connected to WiFi/Ethernet
ifconfig | grep "inet "

# Try pinging Google's DNS
ping -c 3 8.8.8.8

# Try pinging a common website
ping -c 3 google.com
```

If these don't work, you're not connected to the internet.

### Step 2: Check DNS Configuration

```bash
# Check DNS servers (macOS)
scutil --dns | grep nameserver

# Try using Google's DNS temporarily
networksetup -setdnsservers Wi-Fi 8.8.8.8 8.8.4.4

# Or Cloudflare's DNS
networksetup -setdnsservers Wi-Fi 1.1.1.1 1.0.0.1
```

### Step 3: Retry npm Install

Once network is restored:

```bash
cd /Users/duochen/Desktop/career/openPaw/daily-report

# Test npm registry connectivity
npm ping

# If that works, install pdf-parse
npm install pdf-parse

# Should see:
# added 3 packages in 5s
```

### Step 4: Test PDF Parsing

```bash
node test-pdf.js

# Expected output:
# ✅ Parsed PDFs: 1
# 📄 PDF 1:
#   Platform: UberEats
#   Restaurant: [Restaurant Name]
#   Items: [List of items with prices]
```

## 🔄 Alternative: Try Different npm Registry

If your network blocks npm registry:

```bash
# Try taobao mirror (China)
npm config set registry https://registry.npm.taobao.org/
npm install pdf-parse

# Try yarn mirror
npm config set registry https://registry.yarnpkg.com/
npm install pdf-parse

# Reset to default after
npm config set registry https://registry.npmjs.org/
```

## 📦 Alternative: Manual Installation

If npm continues failing, download the package manually:

### Option 1: Use Yarn (if installed)

```bash
# Install yarn if needed
brew install yarn

# Install package
yarn add pdf-parse

# Yarn uses different package managers and might work
```

### Option 2: Download from GitHub

```bash
cd /tmp
curl -L https://github.com/modesty/pdf-parse/archive/refs/tags/v1.1.1.tar.gz -o pdf-parse.tar.gz
tar -xzf pdf-parse.tar.gz
cd pdf-parse-1.1.1
npm install --production

# Copy to your project
cp -r node_modules/pdf-parse /Users/duochen/Desktop/career/openPaw/daily-report/node_modules/
```

### Option 3: Install on Another Computer

If you have another computer with working internet:

```bash
# On working computer
cd /tmp
npm pack pdf-parse
# Creates: pdf-parse-1.1.1.tgz

# Transfer file to this computer (USB, AirDrop, etc.)
# Then install:
npm install /path/to/pdf-parse-1.1.1.tgz
```

## 🎯 Quick Checklist

Before trying npm install again:

- [ ] Check WiFi/Ethernet is connected
- [ ] Can ping `8.8.8.8` (Google DNS)
- [ ] Can ping `google.com` (DNS resolution works)
- [ ] Can ping `registry.npmjs.org` (npm registry reachable)
- [ ] Try `npm ping` (npm can reach registry)
- [ ] No VPN blocking npm traffic
- [ ] No corporate firewall rules

Once all checks pass:
```bash
npm install pdf-parse
node test-pdf.js
```

## ⚡ What Happens When It Works

After successful installation, your daily digest will show:

**Before (without pdf-parse):**
```
🚗 8:28am - Walmart
  Total: $56.86
  ⚠️ Itemized data requires PDF
```

**After (with pdf-parse):**
```
🚗 8:28am - Walmart
  Bananas x2
  420 cal | 3g protein | 81g carbs | 1g fat

  Whole Milk x1
  149 cal | 8g protein | 12g carbs | 8g fat

  Total: $56.86

✅ Parsed from PDF: receipt_f9f77012...pdf
```

## 📞 Still Not Working?

If network issues persist, your nutrition tracking still works for:
- ✅ DoorDash (full itemization)
- ✅ Grubhub (full itemization)
- ⚠️ Uber Eats (total only, until pdf-parse installs)

The system is fully operational - PDF parsing is just an enhancement for Uber Eats!

---

**Current Status**: DNS resolution failing → Cannot reach npm registry → Cannot install pdf-parse

**Solution**: Fix network/DNS → Retry `npm install pdf-parse` → Run `node test-pdf.js`
