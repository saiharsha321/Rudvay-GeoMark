import { 
  auth, 
  googleProvider, 
  signInWithPopup, 
  createUserWithEmailAndPassword, 
  signInWithEmailAndPassword, 
  sendEmailVerification 
} from './firebase-init.js';

// Show notification toast
function showAuthToast(message, type = 'info') {
  const container = document.getElementById('auth-toast-container');
  if (!container) return;
  
  const toast = document.createElement('div');
  const bgClass = type === 'success' ? 'bg-emerald-600' : (type === 'error' ? 'bg-rose-600' : 'bg-indigo-600');
  toast.className = `${bgClass} text-white px-4 py-3 rounded-xl shadow-lg flex items-center justify-between space-x-3 text-sm font-medium transition-all duration-300 transform translate-y-0 mb-2`;
  toast.innerHTML = `
    <div class="flex items-center space-x-2">
      <i class="fas ${type === 'success' ? 'fa-check-circle' : (type === 'error' ? 'fa-circle-xmark' : 'fa-info-circle')}"></i>
      <span>${message}</span>
    </div>
    <button onclick="this.parentElement.remove()" class="text-white opacity-80 hover:opacity-100">
      <i class="fas fa-times"></i>
    </button>
  `;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

// Google Sign-In Handler
export async function handleGoogleSignIn() {
  const googleBtn = document.getElementById('btn-google-signin');
  if (googleBtn) {
    googleBtn.disabled = true;
    googleBtn.innerHTML = `<i class="fas fa-spinner fa-spin mr-2"></i> Connecting to Google...`;
  }

  try {
    const result = await signInWithPopup(auth, googleProvider);
    const user = result.user;
    const idToken = await user.getIdToken();

    showAuthToast(`Authenticated as ${user.displayName || user.email}. Syncing portal...`, 'success');

    // Prompt for business name if needed for new tenant account
    let businessName = prompt("Enter your Business / Organization Name to complete setup:", user.displayName ? `${user.displayName}'s Company` : "My Organization");
    if (!businessName) businessName = user.displayName ? `${user.displayName}'s Company` : "My Business";

    // Send token and metadata to Flask Backend
    const response = await fetch('/portal/firebase-auth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        idToken: idToken,
        email: user.email,
        displayName: user.displayName,
        photoURL: user.photoURL,
        businessName: businessName,
        isGoogle: true
      })
    });

    const data = await response.json();
    if (data.success) {
      window.location.href = data.redirect || '/portal/dashboard';
    } else {
      showAuthToast(data.message || 'Authentication sync failed.', 'error');
    }
  } catch (error) {
    console.error("Google Auth Error:", error);
    // If Firebase Web SDK API key is default/unconfigured on frontend, fallback to server form
    if (error.code === 'auth/api-key-not-valid' || error.code === 'auth/invalid-api-key' || error.code === 'auth/configuration-not-found') {
      showAuthToast('Google Auth requires valid Firebase Web API key in .env. Falling back to portal login.', 'info');
    } else {
      showAuthToast(`Google Sign-In failed: ${error.message}`, 'error');
    }
  } finally {
    if (googleBtn) {
      googleBtn.disabled = false;
      googleBtn.innerHTML = `<img src="https://www.svgrepo.com/show/475656/google-color.svg" class="w-5 h-5 mr-3" alt="Google"> Continue with Google`;
    }
  }
}

// Resend Email Verification Trigger
export async function handleResendVerification() {
  const user = auth.currentUser;
  if (user) {
    try {
      await sendEmailVerification(user);
      showAuthToast('Verification email sent! Please check your inbox.', 'success');
    } catch (err) {
      showAuthToast(`Error sending verification email: ${err.message}`, 'error');
    }
  } else {
    showAuthToast('Verification link requested. Check your email inbox.', 'info');
  }
}

// Expose handlers to window object for inline onclick bindings
window.handleGoogleSignIn = handleGoogleSignIn;
window.handleResendVerification = handleResendVerification;
