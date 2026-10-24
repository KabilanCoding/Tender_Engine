import React, { useEffect, useState, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { CheckCircle2, AlertCircle, ArrowRight, Loader2, X } from 'lucide-react';
import { Scan, ListMagnifyingGlass, Scales, ClipboardText } from '@phosphor-icons/react';
import { tenderApi } from '../api';
import { fetchSettings, loadSettings } from '../../../store/settingsStore';
import { useAuthStore } from '../../../store/authStore';
import { TenderDocumentIcon } from '../components/TenderDocumentIcon';
import { Cpu } from '@phosphor-icons/react'

export const UploadPage: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const [cfg, setCfg] = useState(loadSettings());
  useEffect(() => { fetchSettings().then(setCfg).catch(() => {}); }, []);
  const chosenModel = cfg.tenderModel || cfg.defaultModel;
  const isAdmin = useAuthStore(s => s.role) === 'admin';

  const validateAndSetFile = (file: File) => {
    setErrorMsg(null);
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!['.pdf', '.docx'].includes(ext)) {
      setErrorMsg('Invalid file format. Only PDF and DOCX files are allowed.');
      return;
    }
    if (file.size < 10 * 1024) {
      setErrorMsg('File size too small — minimum 10 KB required.');
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setErrorMsg('File size exceeds the 50 MB limit.');
      return;
    }
    setSelectedFile(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files?.[0]) validateAndSetFile(e.dataTransfer.files[0]);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const res = await tenderApi.uploadTender(selectedFile);
      navigate(`/tender/processing/${res.run_id}`);
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.message || err.message || 'Upload failed. Check that the backend is running.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div className="w-full max-w-[860px] mx-auto pt-6 pb-4 px-4 sm:px-8 space-y-5 animate-fade-up">
      {/* Heading */}
      <div className="space-y-2 text-center">
        <h1 className="text-3xl sm:text-4xl hero-title-wide upload-title">Tender eligibility evaluation</h1>
        <p className="text-sm sm:text-base text-secondary max-w-xl mx-auto leading-relaxed hero-subtitle-custom">
          Upload a tender document. Each eligibility requirement is read, quoted from the tender with its page, and checked against your company records.
        </p>
      </div>

      {/* Upload card - Doppelrand Architecture */}
      <div className="doppelrand-shell">
        <div className="doppelrand-core space-y-3 p-3 sm:p-4">
          {/* Drop zone */}
          <div
            onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => !selectedFile && fileInputRef.current?.click()}
            className={`dropzone-box relative border-2 border-dashed rounded-2xl p-4 sm:p-5 text-center transition-all duration-200 group ${isDragging ? 'dropzone-active' : selectedFile ? 'dropzone-selected' : ''
              }`}
            style={{ cursor: selectedFile ? 'default' : 'pointer' }}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={e => e.target.files?.[0] && validateAndSetFile(e.target.files[0])}
              accept=".pdf,.docx"
              className="hidden"
              id="tender-file-input"
            />

            {selectedFile ? (
              <div className="flex flex-col items-center gap-2 animate-fade-up">
                <TenderDocumentIcon className="w-14 h-14" />
                <div className="space-y-1.5">
                  <div className="text-base font-semibold text-primary">{selectedFile.name}</div>
                  <div className="text-base font-mono text-secondary">{formatSize(selectedFile.size)}</div>
                </div>
                <div className="flex items-center gap-2.5">
                  <CheckCircle2 className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
                  <span className="text-xs font-mono font-semibold text-emerald-700 dark:text-emerald-400">
                    Ready to analyse
                  </span>
                  <button
                    onClick={e => { e.stopPropagation(); setSelectedFile(null); }}
                    className="ml-2 text-slate-400 hover:text-rose-500 transition-colors p-2 rounded-full hover:bg-rose-500/10 cursor-pointer min-w-[44px] min-h-[44px] flex items-center justify-center"
                    title="Remove file"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <TenderDocumentIcon className="w-14 h-14 transition-transform duration-300 group-hover:scale-105" />
                <div className="space-y-0.5">
                  <div className="text-lg font-semibold text-primary">
                    Drag & drop your tender document
                  </div>
                  <div className="text-sm text-secondary font-medium">
                    or{' '}
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="text-indigo-600 dark:text-indigo-400 font-semibold hover:underline underline-offset-2 transition-colors cursor-pointer"
                    >
                      Browse from your device
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <div className="text-xs font-mono font-semibold text-muted">PDF · DOCX · max 50 MB</div>
                </div>
              </div>
            )}
          </div>

          {/* Error */}
          {errorMsg && (
            <div
              className="flex items-start gap-3 p-4 rounded-xl border text-sm animate-fade-up"
              style={{ background: 'var(--bad-bg)', borderColor: 'var(--bad-line)' }}
            >
              <div className="p-2 rounded-xl bg-rose-500/20 text-rose-600 dark:text-rose-400 flex-shrink-0">
                <AlertCircle className="w-6 h-6 text-rose-600 dark:text-rose-400" />
              </div>
              <div className="space-y-1.5 flex-1">
                <div className="font-semibold text-base text-rose-900 dark:text-rose-200">
                  Sorry, please upload a valid tender document.
                </div>
                <div className="text-xs sm:text-sm text-rose-800 dark:text-rose-300 font-mono leading-relaxed bg-rose-500/10 p-3 rounded-xl border border-rose-500/25">
                  {errorMsg}
                </div>
              </div>
            </div>
          )}

          {/* Action bar */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-mono font-semibold text-secondary">
              <Cpu size={19} className="text-[#014BAA] dark:text-[#8FB3F2]" />
              <span>
                AI model: {chosenModel
                  ? <strong className="text-indigo-600">{chosenModel}</strong>
                  : <strong className="text-rose-600">none selected</strong>}
                <span className="text-muted font-normal"> (Settings &gt; AI Model)</span>
                {isAdmin && <Link to="/settings" className="ml-2 text-indigo-600 underline underline-offset-2 font-semibold">change</Link>}
              </span>
            </div>

            <button
              onClick={handleUpload}
              disabled={!selectedFile || isSubmitting}
              className="btn-primary w-full sm:w-auto px-6 py-2 text-sm"
              id="analyse-tender-btn"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>Uploading…</span>
                </>
              ) : (
                <>
                  <span>Analyse tender</span>
                  <span className="btn-icon-wrapper">
                    <ArrowRight className="w-4 h-4" />
                  </span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* What happens next: a sequence, shown as a track */}
      <ol className="upload-steps" aria-label="What happens to the document">
        {[
          { icon: Scan, accent: '#014BAA', title: 'Read', text: 'Every page, including scanned ones.' },
          { icon: ListMagnifyingGlass, accent: '#0f9b8e', title: 'List', text: 'Each requirement with its page and exact wording.' },
          { icon: Scales, accent: '#e07a1f', title: 'Compare', text: 'Against your records: met, not met, missing, or check by hand.' },
          { icon: ClipboardText, accent: '#4f9a2c', title: 'Checklist', text: 'Scope, dates, money and submission rules, for you to compare.' },
        ].map(({ icon: Icon, accent, title, text }, i) => (
          <li key={title} className="upload-step" style={{ ['--accent' as string]: accent }}>
            <span className="upload-step-dot"><Icon size={18} /></span>
            <span className="upload-step-n">0{i + 1}</span>
            <strong>{title}</strong>
            <span className="upload-step-text">{text}</span>
          </li>
        ))}
      </ol>
    </div>
  );
};

