import { reactive } from 'vue'
import * as api from '../api/client.js'

export const auth = reactive({
  loggedIn: !!localStorage.getItem('access_token'),
  loading: false,
  error: '',

  async login(username, password) {
    this.loading = true
    this.error = ''
    try {
      await api.login({ username, password })
      this.loggedIn = true
    } catch (e) {
      this.error = e.message
      throw e
    } finally {
      this.loading = false
    }
  },

  async register(username, email, password) {
    this.loading = true
    this.error = ''
    try {
      await api.register({ username, email, password })
      this.loggedIn = true
    } catch (e) {
      this.error = e.message
      throw e
    } finally {
      this.loading = false
    }
  },

  logout() {
    api.clearTokens()
    this.loggedIn = false
  }
})
