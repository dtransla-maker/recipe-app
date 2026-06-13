/* ─── RecipeSnap — Supabase auth helpers (loaded before app.js) ────── */

const sbClient = window.supabase.createClient(
  window.SUPABASE_URL,
  window.SUPABASE_ANON_KEY
);

async function getSession() {
  const { data: { session } } = await sbClient.auth.getSession();
  return session;
}

/* Redirect to /login when there is no session. Returns the session.
   Handles the magic-link landing case where tokens are still in the
   URL hash and supabase-js hasn't finished storing the session yet. */
async function requireAuth() {
  let session = await getSession();

  if (!session && window.location.hash.includes("access_token")) {
    session = await new Promise((resolve) => {
      const timer = setTimeout(() => resolve(null), 5000);
      sbClient.auth.onAuthStateChange((_event, s) => {
        if (s) { clearTimeout(timer); resolve(s); }
      });
    });
  }

  if (!session) {
    window.location.href = "/login";
    return null;
  }

  const navUser = document.getElementById("nav-user");
  if (navUser) navUser.textContent = session.user.email || "";
  return session;
}

/* fetch() wrapper that attaches the Supabase access token. */
async function authFetch(url, options = {}) {
  const session = await getSession();
  if (!session) {
    window.location.href = "/login";
    throw new Error("Not logged in");
  }
  options.headers = Object.assign({}, options.headers, {
    Authorization: "Bearer " + session.access_token,
  });
  const res = await fetch(url, options);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  return res;
}

async function logout() {
  try { await sbClient.auth.signOut(); } catch (e) { /* ignore */ }
  window.location.href = "/login";
}
