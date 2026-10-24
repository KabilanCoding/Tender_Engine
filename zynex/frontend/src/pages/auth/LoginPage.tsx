import { useCallback, useEffect, useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mail, Lock, Eye, EyeOff, ArrowRight, Loader2, RefreshCw, ShieldCheck as Shield } from 'lucide-react'
import { FileMagnifyingGlass as FileSearch, SealCheck as ShieldCheck, ChartLineUp as BarChart2, HardDrives as Cpu } from '@phosphor-icons/react'
import { useAuthStore } from '../../store/authStore'
import axios from 'axios'

const FEATURES = [
  { Icon: FileSearch,  title: 'Reads every page',          text: 'PDF, DOCX and scanned tenders up to 1000 pages.' },
  { Icon: ShieldCheck, title: 'Checks eligibility',         text: 'Each requirement compared with your company records.' },
  { Icon: BarChart2,   title: 'Estimates cost and effort',  text: 'Modules, sprints and a traceable bid value.' },
  { Icon: Cpu,         title: 'Runs on your own servers',   text: 'Local AI models. No document leaves your network.' },
]

export default function LoginPage() {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState<string | null>(null)
  const [loading, setLoading]   = useState(false)
  const [showPw, setShowPw]     = useState(false)
  const [captcha, setCaptcha]   = useState<{ id: string; svg: string } | null>(null)
  const [code, setCode]         = useState('')

  // a new image for every attempt; the server checks the answer and accepts each image once
  const newCaptcha = useCallback(() => {
    setCode('')
    axios.get('/api/v1/auth/captcha').then(r => setCaptcha({ id: r.data.captcha_id, svg: r.data.svg })).catch(() => setCaptcha(null))
  }, [])
  useEffect(() => { newCaptcha() }, [newCaptcha])
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('username', email)
      params.append('password', password)
      params.append('captcha_id', captcha?.id ?? '')
      params.append('captcha_answer', code)
      const { data } = await axios.post('/api/v1/auth/token', params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      setAuth(data.access_token, data.role, data.full_name)
      navigate('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed. Check your credentials.')
      newCaptcha()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="zx-login min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      {/* Story side */}
      <aside className="zx-login-story relative overflow-hidden hidden lg:flex flex-col justify-between p-12 xl:p-16">
        <div className="zx-login-grid" aria-hidden="true" />
        <div className="zx-login-orb a" aria-hidden="true" />
        <div className="zx-login-orb b" aria-hidden="true" />

        <div className="relative flex items-center gap-3">
          <img src="/zynex-logo.png" alt="" className="h-11 w-11 rounded-full object-cover ring-2 ring-white/20"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
          <span className="text-white text-xl font-semibold" style={{ letterSpacing: '0.28em' }}>ZYNEX</span>
        </div>

        <div className="relative max-w-xl">
          <span className="zx-login-pill"><i aria-hidden="true" /> Offline AI for tenders</span>
          <h1 className="mt-6 text-white font-bold leading-[1.05]" style={{ fontFamily: 'var(--font-heading)', fontSize: 'clamp(2.4rem, 3.6vw, 3.6rem)', letterSpacing: '-0.035em' }}>
            Every tender understood.<br /><span className="zx-login-accent">Every byte stays yours.</span>
          </h1>
          <p className="mt-5 text-[15px] leading-relaxed" style={{ color: 'rgba(248, 243, 240, 0.78)' }}>
            Your tenders, your company data and your AI models all run on your own servers. ZYNEX reads each document, lists every
            requirement with its page, checks it against your records and prepares the estimate and proposal.
          </p>

          <ul className="mt-10 grid grid-cols-2 gap-3">
            {FEATURES.map(({ Icon, title, text }, i) => (
              <li key={title} className="zx-login-feature" style={{ animationDelay: `${150 + i * 90}ms` }}>
                <span className="zx-login-feature-icon"><Icon size={20} /></span>
                <div>
                  <p className="text-white text-sm font-semibold">{title}</p>
                  <p className="text-xs mt-0.5" style={{ color: 'rgba(248, 243, 240, 0.65)' }}>{text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative flex items-center gap-3 text-xs" style={{ color: 'rgba(248, 243, 240, 0.5)' }}>
          <span>Zero-cloud · Your data · Neural estimation · eXecution</span>
        </div>
      </aside>

      {/* Form side */}
      <main className="zx-login-form-side relative flex items-center justify-center px-5 py-12">
        <div className="w-full max-w-[400px] zx-login-in">
          <div className="flex lg:hidden items-center justify-center gap-3 mb-10">
            <img src="/zynex-logo.png" alt="" className="h-12 w-12 rounded-full object-cover"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
            <span className="text-3xl font-semibold" style={{ letterSpacing: '0.24em', color: 'var(--ink)' }}>ZYNEX</span>
          </div>

          <h2 className="font-bold" style={{ fontFamily: 'var(--font-heading)', fontSize: '1.9rem', letterSpacing: '-0.03em', color: 'var(--ink)' }}>Welcome back</h2>
          <p className="mt-1.5 text-sm" style={{ color: 'var(--ink-3)' }}>Sign in with your ZYNEX account to continue.</p>

          {error && (
            <div className="mt-6 text-sm px-4 py-3 rounded-xl border" role="alert"
              style={{ color: 'var(--bad)', background: 'var(--bad-bg)', borderColor: 'var(--bad-line)' }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-5">
            <label className="block">
              <span className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--ink-2)' }}>Email address</span>
              <span className="zx-login-field">
                <Mail size={16} aria-hidden="true" />
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username"
                  placeholder="you@company.com" />
              </span>
            </label>

            <label className="block">
              <span className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--ink-2)' }}>Password</span>
              <span className="zx-login-field">
                <Lock size={16} aria-hidden="true" />
                <input type={showPw ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} required
                  autoComplete="current-password" placeholder="Your password" />
                <button type="button" onClick={() => setShowPw(v => !v)} className="zx-login-eye" aria-label={showPw ? 'Hide password' : 'Show password'}>
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </span>
            </label>

            <div className="block">
              <span className="flex items-center gap-1.5 text-xs font-semibold mb-1.5" style={{ color: 'var(--ink-2)' }}><Shield size={13} /> Security check</span>
              <div className="zx-captcha">
                <div className="zx-captcha-img" aria-label="Security code image" role="img">
                  {captcha ? <img src={`data:image/svg+xml;utf8,${encodeURIComponent(captcha.svg)}`} alt="Type the characters shown" draggable={false} />
                    : <Loader2 size={18} className="animate-spin" />}
                </div>
                <button type="button" className="zx-captcha-new" onClick={newCaptcha} aria-label="Show a new code" title="New code"><RefreshCw size={16} /></button>
              </div>
              <span className="zx-login-field mt-2">
                <Shield size={16} aria-hidden="true" />
                <input value={code} onChange={e => setCode(e.target.value.toUpperCase())} required maxLength={8} autoComplete="off" spellCheck={false}
                  placeholder="Type the 5 characters above" aria-label="Security code" style={{ letterSpacing: '0.2em', fontWeight: 600 }} />
              </span>
            </div>

            <button type="submit" disabled={loading || !captcha} className="zx-login-submit">
              {loading ? <><Loader2 size={16} className="animate-spin" /> Signing in…</> : <>Sign in <ArrowRight size={16} /></>}
            </button>
          </form>

          <div className="mt-10 flex items-center gap-3">
            <span className="h-px flex-1" style={{ background: 'var(--line)' }} />
            <span className="text-[11px] uppercase tracking-[0.18em]" style={{ color: 'var(--ink-3)' }}>Powered by</span>
            <span className="h-px flex-1" style={{ background: 'var(--line)' }} />
          </div>
          <div className="mt-4 flex justify-center">
            <img src="/xenovex-logo.png" alt="Xenovex Technologies" className="h-7 object-contain opacity-80 hover:opacity-100 transition-opacity"
              onError={(e) => {
                const el = e.target as HTMLImageElement
                el.style.display = 'none'
                const fallback = el.nextElementSibling as HTMLElement
                if (fallback) fallback.style.display = 'block'
              }} />
            <span className="hidden text-sm font-semibold" style={{ color: 'var(--brand-blue)' }}>Xenovex Technologies</span>
          </div>
        </div>
      </main>
    </div>
  )
}
