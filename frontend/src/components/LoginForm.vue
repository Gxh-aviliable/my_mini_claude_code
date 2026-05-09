<template>
  <div class="login-overlay">
    <div class="login-card">
      <h1>Enterprise Agent</h1>
      <p class="subtitle">Test Console</p>

      <div class="tabs">
        <button :class="{ active: mode === 'login' }" @click="switchMode('login')">Login</button>
        <button :class="{ active: mode === 'register' }" @click="switchMode('register')">Register</button>
      </div>

      <form @submit.prevent="handleSubmit">
        <div class="field">
          <label>Username</label>
          <input v-model="username" placeholder="Enter username" required />
        </div>
        <div v-if="mode === 'register'" class="field">
          <label>Email</label>
          <input v-model="email" type="email" placeholder="Enter email" required />
        </div>
        <div class="field">
          <label>Password</label>
          <input v-model="password" type="password" placeholder="Enter password" required />
        </div>

        <p v-if="auth.error" class="error">{{ auth.error }}</p>

        <button type="submit" class="btn-primary" :disabled="auth.loading">
          {{ auth.loading ? 'Processing...' : (mode === 'login' ? 'Login' : 'Register') }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { auth } from '../stores/auth.js'

const mode = ref('login')
const username = ref('')
const email = ref('')
const password = ref('')

function switchMode(m) {
  mode.value = m
  auth.error = ''
}

async function handleSubmit() {
  try {
    if (mode.value === 'login') {
      await auth.login(username.value, password.value)
    } else {
      await auth.register(username.value, email.value, password.value)
    }
  } catch {}
}
</script>

<style scoped>
.login-overlay {
  display: flex; align-items: center; justify-content: center;
  min-height: 100vh; background: #1a1a2e;
}
.login-card {
  background: #16213e; border-radius: 12px; padding: 40px;
  width: 400px; max-width: 90vw; box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}
h1 { color: #e0e0e0; text-align: center; margin: 0; font-size: 22px; }
.subtitle { color: #888; text-align: center; margin: 4px 0 20px; font-size: 13px; }
.tabs { display: flex; gap: 8px; margin-bottom: 20px; }
.tabs button {
  flex: 1; padding: 8px; border: 1px solid #333; background: transparent;
  color: #999; border-radius: 6px; cursor: pointer; font-size: 13px;
}
.tabs button.active { background: #0f3460; color: #e0e0e0; border-color: #0f3460; }
.field { margin-bottom: 14px; }
.field label { display: block; color: #aaa; font-size: 12px; margin-bottom: 4px; }
.field input {
  width: 100%; padding: 10px 12px; border-radius: 6px;
  border: 1px solid #333; background: #1a1a2e; color: #e0e0e0;
  font-size: 14px; box-sizing: border-box; outline: none;
}
.field input:focus { border-color: #0f3460; }
.error { color: #e74c3c; font-size: 13px; margin: 0 0 10px; }
.btn-primary {
  width: 100%; padding: 10px; border: none; border-radius: 6px;
  background: #0f3460; color: #e0e0e0; font-size: 14px;
  cursor: pointer; margin-top: 4px;
}
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-primary:hover:not(:disabled) { background: #1a4a7a; }
</style>
