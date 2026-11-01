// Firebase Authentication for Daksh Intelligence.
// 1) Fill in firebaseConfig in firebase-config.js.
// 2) Open this project using VS Code Live Server (not file://).
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js";
import {
  getAuth, setPersistence, browserLocalPersistence, browserSessionPersistence,
  createUserWithEmailAndPassword, signInWithEmailAndPassword, signInWithPopup,
  GoogleAuthProvider, sendPasswordResetEmail, updateProfile, onAuthStateChanged,
  signOut, RecaptchaVerifier, signInWithPhoneNumber
} from "https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js";
import { getFirestore, doc, setDoc, serverTimestamp } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-firestore.js";
import { firebaseConfig } from "./firebase-config.js";

const loginScreen = document.getElementById('loginScreen');
const homeScreen = document.getElementById('homeScreen');
const loginForm = document.getElementById('loginForm');
const usernameInput = document.getElementById('username');
const passcodeInput = document.getElementById('passcode');
const displayNameInput = document.getElementById('displayNameInput');
const nameFieldWrap = document.getElementById('nameFieldWrap');
const confirmFieldWrap = document.getElementById('confirmFieldWrap');
const confirmPasscode = document.getElementById('confirmPasscode');
const phoneAuthPanel = document.getElementById('phoneAuthPanel');
const phoneNumberInput = document.getElementById('phoneNumber');
const otpCodeInput = document.getElementById('otpCode');
const otpWrap = document.getElementById('otpWrap');
const rememberSession = document.getElementById('rememberSession');
const submitAuth = document.getElementById('submitAuth');
const authMessage = document.getElementById('authMessage');
const accountButton = document.getElementById('accountButton');
const accountMenu = document.getElementById('accountMenu');
const accountName = document.getElementById('accountName');
const avatarLetters = document.getElementById('avatarLetters');
const menuUser = document.getElementById('menuUser');
const themeButton = document.getElementById('themeButton');
const wallpaperButton = document.getElementById('wallpaperButton');
const wallpaper = document.querySelector('.wallpaper');

// Robust live wallpaper autoplay & path fallback engine
if (wallpaper) {
  wallpaper.play().catch(() => {});
  const playWallpaperOnce = () => {
    wallpaper.play().catch(() => {});
  };
  document.addEventListener('click', playWallpaperOnce, { once: true });
  document.addEventListener('touchstart', playWallpaperOnce, { once: true });
  document.addEventListener('keydown', playWallpaperOnce, { once: true });
}

const modal = document.getElementById('appModal');
const settingsModal = document.getElementById('settingsModal');
const settingsMessage = document.getElementById('settingsMessage');
const profilePreview = document.getElementById('profilePreview');
const profileFile = document.getElementById('profileFile');
const settingsPhotoUrl = document.getElementById('settingsPhotoUrl');
let authMode = 'login';
let auth;
let db;
let currentUser = null;
let uploadedPhotoDataUrl = '';
let recaptchaVerifier = null;
let phoneConfirmation = null;

function showAuthError(error) {
  const messages = {
    'auth/email-already-in-use': 'An account already exists with this email. Try logging in.',
    'auth/invalid-email': 'Please enter a valid email address.',
    'auth/weak-password': 'Choose a stronger password (at least 6 characters).',
    'auth/invalid-credential': 'Email or password is incorrect.',
    'auth/user-not-found': 'No account was found for that email. Create an account first.',
    'auth/wrong-password': 'Email or password is incorrect.',
    'auth/popup-closed-by-user': 'Google sign-in was closed before completion.',
    'auth/popup-blocked': 'Your browser blocked the Google sign-in popup. Allow popups and try again.',
    'auth/unauthorized-domain': 'This website domain is not authorised in Firebase Authentication settings.',
    'auth/network-request-failed': 'Network error. Check your internet connection and try again.',
    'auth/too-many-requests': 'Too many attempts. Wait a little before trying again.'
  };
  return messages[error?.code] || `Could not complete that action (${error?.code || 'unknown error'}). Check Firebase setup and try again.`;
}

function setMessage(message, target = authMessage, good = false) {
  target.textContent = message;
  target.style.color = good ? '#8ef0bf' : '#ffd3a1';
}
function initials(nameOrEmail) {
  return (nameOrEmail || 'D').split(/[\s@._-]+/).filter(Boolean).map(p => p[0]).join('').slice(0,2).toUpperCase() || 'D';
}
async function saveUserProfile(user, extra = {}) {
  if (!db || !user) return;
  await setDoc(doc(db, 'users', user.uid), {
    uid: user.uid,
    displayName: user.displayName || '',
    email: user.email || '',
    phoneNumber: user.phoneNumber || '',
    photoURL: user.photoURL || '',
    providers: (user.providerData || []).map(p => p.providerId),
    updatedAt: serverTimestamp(),
    ...extra
  }, { merge: true });
}
function renderUser(user) {
  if (!user) return;
  currentUser = user;
  saveUserProfile(user).catch(err => console.error('Could not save Firestore profile:', err));
  const name = user.displayName || user.email?.split('@')[0] || 'Daksh';
  accountName.textContent = name;
  avatarLetters.textContent = initials(name);
  menuUser.textContent = user.email || 'Signed in';
  const photo = user.photoURL || 'daksh-logo.png';
  profilePreview.src = photo;
  settingsName.value = user.displayName || '';
  settingsEmail.textContent = user.email || 'Google account';
  settingsPhotoUrl.value = user.photoURL || '';
  loginScreen.classList.add('hidden');
  homeScreen.classList.remove('hidden');
  syncUserToChat(user);
}
function setAuthMode(mode) {
  authMode = mode;
  const creating = mode === 'create';
  const phoneMode = mode === 'phone';
  document.getElementById('loginTab').classList.toggle('active', mode === 'login');
  document.getElementById('createTab').classList.toggle('active', creating);
  document.getElementById('phoneTab').classList.toggle('active', phoneMode);
  document.getElementById('loginTab').setAttribute('aria-selected', String(mode === 'login'));
  document.getElementById('createTab').setAttribute('aria-selected', String(creating));
  document.getElementById('phoneTab').setAttribute('aria-selected', String(phoneMode));
  loginForm.classList.toggle('hidden', phoneMode);
  phoneAuthPanel.classList.toggle('hidden', !phoneMode);
  document.getElementById('forgotPassword').classList.toggle('hidden', creating || phoneMode);
  document.getElementById('googleButton').classList.toggle('hidden', phoneMode);
  document.querySelector('.auth-divider').classList.toggle('hidden', phoneMode);
  nameFieldWrap.classList.toggle('hidden', !creating);
  displayNameInput.required = creating;
  confirmFieldWrap.classList.toggle('hidden', !creating);
  confirmPasscode.required = creating;
  passcodeInput.autocomplete = creating ? 'new-password' : 'current-password';
  submitAuth.innerHTML = creating ? 'Create secure account <span>↗</span>' : 'Enter workspace <span>↗</span>';
  setMessage('');
}
document.getElementById('loginTab').addEventListener('click', () => setAuthMode('login'));
document.getElementById('createTab').addEventListener('click', () => setAuthMode('create'));
document.getElementById('phoneTab').addEventListener('click', () => setAuthMode('phone'));

try {
  const app = initializeApp(firebaseConfig);
  auth = getAuth(app);
  db = getFirestore(app);
} catch (error) {
  setMessage('Firebase is not configured yet. Open firebase-config.js and add your Firebase project settings.');
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!auth) return setMessage('Firebase setup required. Follow SETUP-FIREBASE.txt.');
  const email = usernameInput.value.trim().toLowerCase();
  const password = passcodeInput.value;
  try {
    await setPersistence(auth, rememberSession.checked ? browserLocalPersistence : browserSessionPersistence);
    if (authMode === 'create') {
      if (password !== confirmPasscode.value) return setMessage('The passwords do not match.');
      if (password.length < 6) return setMessage('Use a password with at least 6 characters.');
      const credential = await createUserWithEmailAndPassword(auth, email, password);
      const displayName = displayNameInput.value.trim();
      if (displayName) await updateProfile(credential.user, { displayName });
      renderUser(auth.currentUser);
      loginForm.reset();
      rememberSession.checked = true;
    } else {
      await signInWithEmailAndPassword(auth, email, password);
      renderUser(auth.currentUser);
      loginForm.reset();
      rememberSession.checked = true;
    }
    setMessage('');
  } catch (error) {
    setMessage(showAuthError(error));
  }
});

document.getElementById('sendOtpButton').addEventListener('click', async () => {
  if (!auth) return setMessage('Firebase setup required. Follow SETUP-FIREBASE.txt.');
  const phoneNumber = phoneNumberInput.value.trim().replace(/[\s()-]/g, '');
  if (!/^\+[1-9]\d{7,14}$/.test(phoneNumber)) return setMessage('Enter a valid international phone number, for example +919876543210.');
  try {
    await setPersistence(auth, rememberSession.checked ? browserLocalPersistence : browserSessionPersistence);
    if (recaptchaVerifier) { try { await recaptchaVerifier.clear(); } catch {} }
    recaptchaVerifier = new RecaptchaVerifier(auth, 'recaptcha-container', { size: 'normal' });
    await recaptchaVerifier.render();
    phoneConfirmation = await signInWithPhoneNumber(auth, phoneNumber, recaptchaVerifier);
    otpWrap.classList.remove('hidden');
    setMessage('SMS verification code sent. Enter it below.', authMessage, true);
  } catch (error) {
    setMessage(showAuthError(error));
    if (recaptchaVerifier) { try { await recaptchaVerifier.clear(); } catch {} recaptchaVerifier = null; }
  }
});
document.getElementById('verifyOtpButton').addEventListener('click', async () => {
  if (!phoneConfirmation) return setMessage('Send a verification code first.');
  const code = otpCodeInput.value.trim();
  if (!code) return setMessage('Enter the SMS verification code.');
  try {
    const result = await phoneConfirmation.confirm(code);
    await saveUserProfile(result.user, { phoneVerifiedAt: serverTimestamp() });
    renderUser(result.user);
    phoneConfirmation = null;
    otpCodeInput.value = '';
    setMessage('');
  } catch (error) { setMessage(showAuthError(error)); }
});

document.getElementById('googleButton').addEventListener('click', async () => {
  if (!auth) return setMessage('Firebase setup required. Follow SETUP-FIREBASE.txt.');
  try {
    await setPersistence(auth, rememberSession.checked ? browserLocalPersistence : browserSessionPersistence);
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: 'select_account' });
    await signInWithPopup(auth, provider);
    setMessage('');
  } catch (error) {
    setMessage(showAuthError(error));
  }
});

document.getElementById('forgotPassword').addEventListener('click', async () => {
  if (!auth) return setMessage('Firebase setup required. Follow SETUP-FIREBASE.txt.');
  const email = usernameInput.value.trim().toLowerCase();
  if (!email) return setMessage('Enter your email address first, then click Forgot password.');
  try {
    await sendPasswordResetEmail(auth, email);
    setMessage('If an account exists for that email, a password reset message has been sent. Check your inbox and spam folder.', authMessage, true);
  } catch (error) {
    setMessage(showAuthError(error));
  }
});

onAuthStateChanged(auth, user => {
  if (user) renderUser(user);
  else {
    currentUser = null;
    const chatScreen = document.getElementById('chatScreen');
    if (chatScreen) {
      chatScreen.classList.add('hidden');
      chatScreen.style.display = 'none';
    }
    homeScreen.classList.add('hidden');
    loginScreen.classList.remove('hidden');
  }
});

accountButton.addEventListener('click', () => {
  const willOpen = accountMenu.classList.contains('hidden');
  accountMenu.classList.toggle('hidden');
  accountButton.setAttribute('aria-expanded', String(willOpen));
});
document.addEventListener('click', event => {
  if (!event.target.closest('.topbar-right')) {
    accountMenu.classList.add('hidden');
    accountButton.setAttribute('aria-expanded', 'false');
  }
});
themeButton.addEventListener('click', () => {
  document.body.classList.toggle('light-theme');
  const isLight = document.body.classList.contains('light-theme');
  themeButton.innerHTML = `${isLight ? 'Switch to dark theme' : 'Switch to light theme'} <span>◐</span>`;
});
wallpaperButton.addEventListener('click', () => {
  if (wallpaper.paused) {
    wallpaper.play().catch(() => {});
    wallpaperButton.innerHTML = 'Pause live wallpaper <span>Ⅱ</span>';
  } else {
    wallpaper.pause();
    wallpaperButton.innerHTML = 'Play live wallpaper <span>▶</span>';
  }
});
document.getElementById('logoutButton').addEventListener('click', async () => {
  accountMenu.classList.add('hidden');
  modal.classList.add('hidden');
  settingsModal.classList.add('hidden');
  if (auth) { try { await signOut(auth); } catch (e) { setMessage(showAuthError(e)); } }
});

document.getElementById('settingsButton').addEventListener('click', () => {
  accountMenu.classList.add('hidden');
  if (currentUser) renderUser(currentUser);
  settingsMessage.textContent = '';
  settingsModal.classList.remove('hidden');
});
function closeSettings(){ settingsModal.classList.add('hidden'); uploadedPhotoDataUrl = ''; }
document.getElementById('closeSettings').addEventListener('click', closeSettings);
settingsModal.addEventListener('click', event => { if (event.target === settingsModal) closeSettings(); });

profileFile.addEventListener('change', () => {
  const file = profileFile.files?.[0];
  if (!file) return;
  if (!['image/png','image/jpeg','image/webp'].includes(file.type)) {
    setMessage('Choose a PNG, JPG, or WebP image.', settingsMessage); profileFile.value = ''; return;
  }
  if (file.size > 2 * 1024 * 1024) {
    setMessage('That image is larger than 2 MB. Please choose a smaller image.', settingsMessage); profileFile.value = ''; return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    uploadedPhotoDataUrl = reader.result;
    profilePreview.src = uploadedPhotoDataUrl;
    settingsPhotoUrl.value = '';
    setMessage('Preview ready. Save settings to apply this profile picture for this session.', settingsMessage, true);
  };
  reader.readAsDataURL(file);
});

document.getElementById('settingsForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (!currentUser) return;
  const displayName = document.getElementById('settingsName').value.trim();
  const photoURL = settingsPhotoUrl.value.trim();
  // A locally selected image is preview-only without Firebase Storage. Persist URL/name via Auth profile.
  const profile = { displayName: displayName || null };
  if (photoURL) profile.photoURL = photoURL;
  else if (uploadedPhotoDataUrl) {
    setMessage('A local photo preview is selected, but permanent uploads need Firebase Storage. Add a profile image URL or configure Storage to save it permanently.', settingsMessage);
    return;
  }
  try {
    await updateProfile(currentUser, profile);
    await saveUserProfile(currentUser);
    renderUser(currentUser);
    setMessage('Account profile updated.', settingsMessage, true);
  } catch (error) {
    setMessage(showAuthError(error), settingsMessage);
  }
});
document.getElementById('changePassword').addEventListener('click', async () => {
  if (!currentUser?.email) return setMessage('No email address is available for password reset.', settingsMessage);
  try {
    await sendPasswordResetEmail(auth, currentUser.email);
    setMessage('Password reset email sent. Check your inbox and spam folder.', settingsMessage, true);
  } catch (error) {
    setMessage(showAuthError(error), settingsMessage);
  }
});

const descriptions = {
  'AI Chat': 'A dedicated chat interface for asking questions, brainstorming, writing, and exploring ideas. The AI backend can be connected in the next development step.',
  'EduPer with Daksh': 'A focused study companion for chapter notes, concept explanations, practice questions, revision plans, and exam preparation.',
  'Commanding Studio': 'A developer workspace concept for Python, code editing, terminal tools, and project building. A real code editor and safe execution environment still need to be integrated.'
};
const symbols = {'AI Chat':'✳','EduPer with Daksh':'⌁','Commanding Studio':'⌘'};
document.querySelectorAll('.app-card').forEach(card => card.addEventListener('click', () => {
  const app = card.dataset.app;
  if (app === 'AI Chat') {
    // 🤖 1. AI Chat: Opens directly when selected, without asking user to log in again!
    openAIChatApp();
    return;
  }

  // 2. EduPer with Daksh & 3. Coding Workspace: Info modal (will be added next)
  document.getElementById('modalTitle').textContent = app;
  document.getElementById('modalDescription').textContent = descriptions[app] || '';
  document.getElementById('modalSymbol').textContent = symbols[app] || '✦';
  const notice = document.querySelector('.modal-notice');
  if (notice) {
    notice.innerHTML = `<span class="status-dot"></span> In Active Development · This module will be added in the next update!`;
  }
  modal.classList.remove('hidden');
}));
function closeModal(){ modal.classList.add('hidden'); }
document.getElementById('closeModal').addEventListener('click', closeModal);
document.getElementById('backHome').addEventListener('click', closeModal);
modal.addEventListener('click', event => { if (event.target === modal) closeModal(); });
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    closeModal(); closeSettings();
    accountMenu.classList.add('hidden');
  }
});


// ================= WORKSPACE INTERFACE FLOW CONTROLLER =================

function openAIChatApp() {
  const home = document.getElementById('homeScreen');
  if (home) {
    home.classList.add('hidden');
    home.style.display = 'none';
  }
  const login = document.getElementById('loginScreen');
  if (login) {
    login.classList.add('hidden');
    login.style.display = 'none';
  }

  const chatScreen = document.getElementById('chatScreen');
  if (chatScreen) {
    chatScreen.classList.remove('hidden');
    chatScreen.style.display = 'flex';
  }

  const appLayout = document.getElementById('app-main-layout');
  if (appLayout) {
    appLayout.classList.remove('hidden');
    appLayout.style.display = 'flex';
  }

  const viewChat = document.getElementById('view-chat');
  if (viewChat) {
    viewChat.classList.remove('hidden');
  }

  if (currentUser && window.syncUserToChat) {
    window.syncUserToChat(currentUser);
  }

  // Ensure active conversation exists so chat doesn't render blank
  if (window.appState) {
    if (!window.appState.conversations || window.appState.conversations.length === 0) {
      const initialSession = { id: `session-${Date.now()}`, title: 'Workstation Session', messages: [] };
      window.appState.conversations = [initialSession];
      window.appState.activeConversationId = initialSession.id;
    }
  }

  if (window.renderConversationsList) {
    window.renderConversationsList();
  }
  if (window.renderMessages) {
    window.renderMessages();
  }
  if (window.applySidebarState) {
    window.applySidebarState();
  }
  if (window.lucide) {
    window.lucide.createIcons();
  }
  if (window.scrollChatToBottom) {
    window.scrollChatToBottom();
  }
}

function returnToDashboard() {
  const chatScreen = document.getElementById('chatScreen');
  if (chatScreen) {
    chatScreen.classList.add('hidden');
    chatScreen.style.display = 'none';
  }
  const homeScreen = document.getElementById('homeScreen');
  if (homeScreen) {
    homeScreen.classList.remove('hidden');
    homeScreen.style.display = '';
  }
}

function syncUserToChat(user) {
  if (!user) return;
  const name = user.displayName || user.email?.split('@')[0] || 'Daksh Bugalia';
  const initial = (name[0] || 'D').toUpperCase();
  const avatarUrl = user.photoURL || '';

  const headAvatar = document.getElementById('header-avatar');
  if (headAvatar) {
    if (avatarUrl && !avatarUrl.includes('daksh-logo.png')) {
      headAvatar.innerHTML = `<img src="${avatarUrl}" class="w-full h-full object-cover rounded-full">`;
    } else {
      headAvatar.innerText = initial;
    }
  }
  const headUser = document.getElementById('header-username');
  if (headUser) headUser.innerText = name;

  const sideAvatar = document.getElementById('sidebar-avatar');
  if (sideAvatar) {
    if (avatarUrl && !avatarUrl.includes('daksh-logo.png')) {
      sideAvatar.innerHTML = `<img src="${avatarUrl}" class="w-full h-full object-cover rounded-full">`;
    } else {
      sideAvatar.innerText = initial;
    }
  }
  const sideUser = document.getElementById('sidebar-username');
  if (sideUser) sideUser.innerText = name;

  const mobAvatar = document.getElementById('mobile-sidebar-avatar');
  if (mobAvatar) {
    if (avatarUrl && !avatarUrl.includes('daksh-logo.png')) {
      mobAvatar.innerHTML = `<img src="${avatarUrl}" class="w-full h-full object-cover rounded-xl">`;
    } else {
      mobAvatar.innerText = initial;
    }
  }
  const mobUser = document.getElementById('mobile-sidebar-username');
  if (mobUser) mobUser.innerText = name;

  const sessionObj = {
    id: user.uid || 'usr-active',
    name: name,
    email: user.email || 'user@workspace.local',
    role: 'Verified Member',
    isOwner: (user.email || '').toLowerCase().includes('dakshbugalia1'),
    photoURL: avatarUrl
  };

  if (window.currentUser !== undefined) {
    window.currentUser = sessionObj;
  }

  localStorage.setItem('daksh_auth_session', JSON.stringify(sessionObj));
}

// Attach to window so inline onclick handlers can call them
window.openAIChatApp = openAIChatApp;
window.returnToDashboard = returnToDashboard;
window.syncUserToChat = syncUserToChat;

// Menu button to open chat
const openChatMenuBtn = document.getElementById('openChatMenuButton');
if (openChatMenuBtn) {
  openChatMenuBtn.addEventListener('click', () => {
    accountMenu.classList.add('hidden');
    openAIChatApp();
  });
}

// Instant Guest Access button on login screen
const guestBtn = document.getElementById('guestAccessButton');
if (guestBtn) {
  guestBtn.addEventListener('click', () => {
    const guestUser = {
      uid: `guest-${Date.now()}`,
      displayName: 'Daksh Guest',
      email: 'guest@daksh.workspace',
      photoURL: 'daksh-logo.png',
      isGuest: true
    };
    renderUser(guestUser);
  });
}

// Check saved session on startup
document.addEventListener('DOMContentLoaded', () => {
  try {
    const saved = localStorage.getItem('daksh_auth_session');
    if (saved && !currentUser) {
      const parsed = JSON.parse(saved);
      if (parsed && parsed.email) {
        renderUser({
          uid: parsed.id || 'usr-saved',
          displayName: parsed.name,
          email: parsed.email,
          photoURL: parsed.photoURL || ''
        });
      }
    }
  } catch (e) {}
});
