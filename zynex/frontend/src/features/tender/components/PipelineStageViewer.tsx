import React, { useState, useEffect } from 'react';
import { tenderApi, PipelineStageArtifact } from '../api';
import { Code, CheckCircle, Copy, Check, Terminal, Layers, FileJson } from 'lucide-react';

interface PipelineStageViewerProps {
  runId: string;
}

export const PipelineStageViewer: React.FC<PipelineStageViewerProps> = ({ runId }) => {
  const [stages, setStages] = useState<PipelineStageArtifact[]>([]);
  const [selectedStage, setSelectedStage] = useState<PipelineStageArtifact | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const loadStages = async () => {
      try {
        setLoading(true);
        const res = await tenderApi.getStageArtifacts(runId);
        if (res && res.stages && res.stages.length > 0) {
          setStages(res.stages);
          setSelectedStage(res.stages[0]);
        }
      } catch (err) {
        console.error('Failed to load stage artifacts', err);
      } finally {
        setLoading(false);
      }
    };
    if (runId) {
      loadStages();
    }
  }, [runId]);

  const handleCopy = (jsonContent: string) => {
    navigator.clipboard.writeText(jsonContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="glass-panel p-6 rounded-2xl border border-mid text-center py-12">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm text-secondary font-mono">Loading Pipeline Stage JSON Artifacts...</p>
      </div>
    );
  }

  if (!stages || stages.length === 0) {
    return null;
  }

  return (
    <div className="glass-panel p-6 rounded-2xl border border-mid space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-mid pb-4">
        <div>
          <h3 className="text-xl font-semibold text-primary flex items-center gap-2">
            <FileJson className="w-6 h-6 text-indigo-500" />
            Pipeline Stage Data (JSON Inspector)
          </h3>
          <p className="text-xs text-secondary mt-1">
            Click any step button below to view its stage output JSON payload in real time.
          </p>
        </div>

        <span className="section-tag">
          <Terminal className="w-3.5 h-3.5" />
          {stages.length} Pipeline Stages
        </span>
      </div>

      {/* 12 Stage Buttons Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
        {stages.map((stage) => {
          const isSelected = selectedStage?.stage_id === stage.stage_id;
          return (
            <button
              key={stage.stage_id}
              onClick={() => setSelectedStage(stage)}
              className={`p-3 rounded-xl border text-left transition-all flex flex-col justify-between gap-2 cursor-pointer ${
                isSelected
                  ? 'bg-indigo-600 text-white border-indigo-600 shadow-md shadow-indigo-500/20 scale-[1.02]'
                  : 'bg-raised border-mid hover:border-indigo-500/40 text-primary'
              }`}
            >
              <div className="flex items-center justify-between w-full">
                <span className={`text-xs font-mono font-semibold px-2 py-0.5 rounded ${
                  isSelected ? 'bg-indigo-700 text-white' : 'bg-surface text-indigo-600 dark:text-indigo-400 border border-mid'
                }`}>
                  {stage.stage_id}
                </span>
                <span className={`flex items-center gap-1 text-[10px] font-semibold ${
                  isSelected ? 'text-emerald-200' : 'text-emerald-600 dark:text-emerald-400'
                }`}>
                  <CheckCircle className="w-3 h-3" />
                  {stage.status}
                </span>
              </div>
              <span className={`text-xs font-semibold truncate leading-tight ${isSelected ? 'text-white' : 'text-primary'}`}>
                {stage.step.replace(/^[S\d[a-z]+\s*/, '')}
              </span>
            </button>
          );
        })}
      </div>

      {/* Selected Stage JSON Output Inspector */}
      {selectedStage && (
        <div className="rounded-xl border border-mid overflow-hidden bg-surface shadow-sm">
          {/* Action Sub-bar */}
          <div className="bg-raised px-4 py-3 border-b border-mid flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Code className="w-4 h-4 text-indigo-500" />
              <span className="font-semibold text-sm text-primary">{selectedStage.step}</span>
              <span className="text-xs text-secondary font-mono">({selectedStage.status})</span>
            </div>

            <button
              onClick={() => handleCopy(JSON.stringify(selectedStage.output, null, 2))}
              className="px-3 py-1.5 bg-surface hover:bg-raised text-primary text-xs font-semibold rounded-lg border border-mid flex items-center gap-1.5 transition-all cursor-pointer shadow-sm"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-500" />
                  Copied!
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5 text-secondary" />
                  Copy JSON
                </>
              )}
            </button>
          </div>

          {/* JSON Block */}
          <div className="p-4 max-h-96 overflow-y-auto font-mono text-xs text-indigo-700 dark:text-indigo-300 leading-relaxed bg-raised/50 select-all scrollbar-thin">
            <pre>{JSON.stringify(selectedStage.output, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
};
