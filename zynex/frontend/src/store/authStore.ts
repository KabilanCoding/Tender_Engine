import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  token: string | null
  role: string | null
  fullName: string | null
  isAuthenticated: boolean
  setAuth: (token: string, role: string, fullName: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      role: null,
      fullName: null,
      isAuthenticated: false,
      setAuth: (token, role, fullName) =>
        set({ token, role, fullName, isAuthenticated: true }),
      logout: () =>
        set({ token: null, role: null, fullName: null, isAuthenticated: false }),
    }),
    { name: 'zynex-auth' }
  )
)
