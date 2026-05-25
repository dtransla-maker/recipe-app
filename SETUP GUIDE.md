# RecipeSnap — Step-by-Step Setup Guide

Your app is fully built. Now you just need to create 4 free accounts, get your API keys, and upload the app to Replit. Follow each step in order.

---

## STEP 1 — Create a Supabase account (your recipe database)

Supabase stores all your saved recipes in the cloud for free.

1. Go to **https://supabase.com** and click **Start your project**
2. Sign up with your Google account (easiest)
3. Click **New project**
4. Fill in:
   - **Name**: `recipesnap` (or anything you like)
   - **Database Password**: create a strong password and save it somewhere safe
   - **Region**: choose the one closest to you
5. Click **Create new project** — wait about 1 minute for it to set up
6. Once ready, click **SQL Editor** in the left sidebar
7. Click **New query**
8. Open the file `supabase_setup.sql` from your project folder and copy ALL of its contents
9. Paste it into the SQL editor and click **Run**
   - You should see "Success. No rows returned" — that means it worked!
10. Now go to **Project Settings** (gear icon in left sidebar) → **API**
11. Copy and save these two values — you'll need them later:
    - **Project URL** (looks like `https://abcxyz.supabase.co`)
    - **anon public** key (long string under "Project API keys")

---

## STEP 2 — Create an AssemblyAI account (video transcription)

AssemblyAI converts video speech into text so Claude can read it. Free plan gives you 5 hours/month.

1. Go to **https://www.assemblyai.com** and click **Get started for free**
2. Sign up with your email or Google account
3. Once logged in, you'll see your **API Key** right on the dashboard
4. Copy and save that API key — you'll need it later

---

## STEP 3 — Create an Anthropic API account (recipe AI)

This is separate from your Claude desktop app. It's what lets the app call Claude to extract recipes.

1. Go to **https://console.anthropic.com**
2. Sign in with your existing Anthropic account, or create a new one with your email
3. Once logged in, click **API Keys** in the left sidebar
4. Click **Create Key**
5. Give it a name like `recipesnap`
6. Copy and save the key shown (starts with `sk-ant-...`) — it's only shown once!
7. You may need to add a payment method for billing — but the cost is tiny, around $0.001 per recipe

---

## STEP 4 — Upload the app to Replit

Replit runs your app in the cloud so you can access it from any browser or phone.

1. Go to **https://replit.com** and click **Sign up**
2. Create a free account with your Google or GitHub account
3. Once logged in, click the **+ Create Repl** button (top left)
4. Choose **Import from GitHub** — OR if you don't have GitHub, select **Python** as the template
5. **If using GitHub:**
   - Skip to the GitHub section below first, then return here
6. **If using Python template:**
   - Name it `recipesnap`
   - After it creates, you'll see a file editor on the left side
   - Delete the default `main.py` file
   - Now upload each file from your project folder:
     - Click the three dots `⋯` next to "Files" → **Upload file**
     - Upload these files one by one:
       - `app.py`
       - `requirements.txt`
       - `.replit`
     - Create a `templates` folder: click `⋯` → **Add folder** → name it `templates`
     - Upload the 3 HTML files into the templates folder:
       - `index.html`, `library.html`, `recipe.html`
     - Create a `static` folder and upload into it:
       - `styles.css`, `app.js`

---

## STEP 5 — Add your API keys to Replit (Secrets)

Never paste API keys directly into code. Replit has a secure "Secrets" vault.

1. In your Replit project, look for the **🔒 Secrets** icon in the left toolbar (looks like a padlock)
2. Click it, then add each of these — one at a time:

   | Key name | Value |
   |---|---|
   | `SUPABASE_URL` | Your Supabase Project URL from Step 1 |
   | `SUPABASE_KEY` | Your Supabase anon public key from Step 1 |
   | `ANTHROPIC_API_KEY` | Your Anthropic key from Step 3 |
   | `ASSEMBLYAI_API_KEY` | Your AssemblyAI key from Step 2 |

3. For each one: type the **Key name** exactly as shown → paste the **Value** → click **Add Secret**

---

## STEP 6 — Install packages and run

1. In Replit, click the **Shell** tab (bottom panel)
2. Type this command and press Enter:
   ```
   pip install -r requirements.txt
   ```
3. Wait for all packages to install (takes about 1-2 minutes)
4. Click the green **▶ Run** button at the top
5. A preview window should appear on the right showing your RecipeSnap app!
6. Click the **↗ Open in new tab** button to see it full screen

---

## STEP 7 — Test it!

1. Find any public cooking video on YouTube, TikTok, Instagram, or Facebook
2. Copy the video URL
3. Paste it into your RecipeSnap app and click **Get Recipe**
4. Wait 30–60 seconds (first run is slower)
5. Review the extracted recipe and click **Save to My Recipes**
6. Go to **My Recipes** to see your recipe book!

---

## Accessing from your phone

Once your Replit app is running:
1. In Replit, click the web preview's **Open in new tab** button
2. Copy that URL (it looks like `https://recipesnap.yourusername.repl.co`)
3. Open that URL on your phone — it works like a mobile app!
4. On iPhone: tap Share → **Add to Home Screen** to make it feel like an app

---

## Tips & Troubleshooting

**The app says "video is private"**
→ Only public videos work. Make sure the video isn't set to private or friends-only.

**Instagram or Facebook videos aren't working**
→ These platforms have stricter access rules. Try YouTube or TikTok first — they work most reliably.

**The recipe extraction is slow (1-2 minutes)**
→ This happens when the video has no captions and audio must be downloaded and transcribed. YouTube videos with captions are nearly instant.

**"API key not found" error**
→ Double-check that all 4 Secrets are added in Replit with the exact key names shown in Step 5.

**App stops after Replit goes to sleep (free plan)**
→ Free Replit apps pause after inactivity. Just visit the URL again and it will restart in ~30 seconds. To keep it always-on, consider Replit's $7/month plan or ask me about free alternatives.

---

## Cost Summary

| Service | Free Tier | What you get |
|---|---|---|
| Supabase | Free forever | 500MB database, unlimited recipes |
| AssemblyAI | 5 hours/month free | ~100 recipe videos/month |
| Anthropic API | ~$0.001 per recipe | 1000 recipes costs ~$1 |
| Replit | Free (sleeps when idle) | Runs your app in the cloud |

**Estimated monthly cost for typical home use: $0–$2**

---

*Built with ❤️ using Flask, Claude AI, AssemblyAI, and Supabase*
