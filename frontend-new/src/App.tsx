import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { 
  Briefcase, 
  MapPin, 
  Clock, 
  ExternalLink, 
  DollarSign, 
  Filter, 
  Search,
  Globe,
  TrendingUp,
  Layout,
  Upload,
  User,
  CheckCircle,
  FileText,
  AlertCircle,
  Zap,
  History
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

interface Job {
  id: string;
  source: string;
  job_title: string;
  company: string;
  location: string;
  remote: boolean;
  posted_date: string;
  url: string;
  description: string;
  salary?: string;
  applicants_count?: number;
}

interface Summary {
  total_discovered: number;
  total_deduplicated: number;
  by_source: Record<string, number>;
}

const App: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const [isDiscovering, setIsDiscovering] = useState(false);
  const [lastDiscovery, setLastDiscovery] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'all' | 'unique'>('unique');
  
  const [cvProfile, setCvProfile] = useState<any>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isApplying, setIsApplying] = useState<string | null>(null);
  const [showReviewOverlay, setShowReviewOverlay] = useState(false);
  const [tracker, setTracker] = useState<any>({ applied_count: 0, failed_count: 0, applications: [] });

  const fetchContent = async () => {
    try {
      const [jobsRes, summaryRes, statusRes, profileRes, trackerRes] = await Promise.all([
        axios.get(`${API_BASE}/jobs?mode=${viewMode}`),
        axios.get(`${API_BASE}/summary`),
        axios.get(`${API_BASE}/discover/status`),
        axios.get(`${API_BASE}/cv/profile`),
        axios.get(`${API_BASE}/apply/tracker`)
      ]);
      setJobs(jobsRes.data);
      setSummary(summaryRes.data);
      setTracker(trackerRes.data);
      setIsDiscovering(statusRes.data.running);
      if (statusRes.data.last_run) setLastDiscovery(statusRes.data.last_run);
      if (profileRes.data && typeof profileRes.data === 'object' && Object.keys(profileRes.data).length > 0) {
        setCvProfile(profileRes.data);
      }
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      setIsUploading(true);
      const res = await axios.post(`${API_BASE}/cv/upload`, formData);
      setCvProfile(res.data.profile);
      alert('CV uploaded and parsed successfully!');
    } catch (error) {
      console.error('Upload failed:', error);
      alert('Failed to process CV. Make sure GEMINI_API_KEY is set.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleStartDiscovery = async () => {
    try {
      setIsDiscovering(true);
      await axios.post(`${API_BASE}/discover`);
      // Start polling for status
      const interval = setInterval(async () => {
        const statusRes = await axios.get(`${API_BASE}/discover/status`);
        if (!statusRes.data.running) {
          clearInterval(interval);
          setIsDiscovering(false);
          fetchContent(); // Refresh data when done
        }
      }, 5000);
    } catch (error) {
      console.error('Failed to start discovery:', error);
      setIsDiscovering(false);
    }
  };

  const handleApply = async (jobId: string) => {
    try {
      setIsApplying(jobId);
      await axios.post(`${API_BASE}/apply/bulk`, [jobId]);
      setShowReviewOverlay(true);
    } catch (error) {
      console.error('Application failed:', error);
      alert('Failed to start application process.');
      setIsApplying(null);
    }
  };

  const handleBulkApply = async () => {
    const jobIds = filteredJobs.slice(0, 10).map(j => j.id); // Apply to first 10 for safety
    if (jobIds.length === 0) return;
    
    try {
      setIsApplying('bulk');
      await axios.post(`${API_BASE}/apply/bulk`, jobIds);
      setShowReviewOverlay(true);
    } catch (error) {
      console.error('Bulk apply failed:', error);
      alert('Failed to start bulk application.');
      setIsApplying(null);
    }
  };

  const handleReviewComplete = async () => {
    try {
      await axios.post(`${API_BASE}/apply/review/complete`);
      // We don't close the overlay here if in bulk mode, 
      // but the backend will wait for the next signal anyway.
      // For now, let's keep it open until the human manually closes or all are done.
      fetchContent();
    } catch (error) {
      console.error('Failed to complete review:', error);
    }
  };

  useEffect(() => {
    fetchContent();
    const interval = setInterval(fetchContent, 30000);
    return () => clearInterval(interval);
  }, [viewMode]);

  const filteredJobs = jobs.filter(job => 
    job.job_title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    job.company.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="container">
      <header>
        <div className="logo-section">
          <motion.h1 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            Job Bot Intelligence
          </motion.h1>
          <p>Daily discovery for Data Engineering roles</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div className="search-box" style={{ 
            background: 'var(--card-bg)', 
            padding: '0.5rem 1rem', 
            borderRadius: '0.75rem', 
            display: 'flex', 
            alignItems: 'center', 
            gap: '0.5rem',
            border: '1px solid var(--glass-border)'
          }}>
            <Search size={18} color="var(--text-secondary)" />
            <input 
              type="text" 
              placeholder="Search roles..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{ background: 'transparent', border: 'none', color: 'white', outline: 'none', width: '200px' }}
            />
          </div>

          <label className={`btn ${isUploading ? 'btn-outline' : 'btn-primary'}`} style={{ cursor: 'pointer' }}>
            {isUploading ? <Clock size={18} /> : <Upload size={18} />}
            {cvProfile ? 'Update CV' : 'Upload CV'}
            <input type="file" hidden onChange={handleFileUpload} accept=".pdf,.docx" />
          </label>

          <button 
            className={`btn ${isDiscovering ? 'btn-outline' : 'btn-primary'}`}
            onClick={handleStartDiscovery}
            disabled={isDiscovering}
            style={{ minWidth: '160px', justifyContent: 'center' }}
          >
            {isDiscovering ? (
              <>
                <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}>
                  <Clock size={18} />
                </motion.div>
                Scanning...
              </>
            ) : (
              <>
                <TrendingUp size={18} />
                Start Discovery
              </>
            )}
          </button>
        </div>
      </header>

      {cvProfile && (
        <motion.div 
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          style={{ 
            background: 'rgba(16, 185, 129, 0.1)', 
            border: '1px solid var(--success)', 
            padding: '0.75rem 1.5rem', 
            borderRadius: '1rem', 
            marginBottom: '2rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{ background: 'var(--success)', padding: '0.5rem', borderRadius: '50%' }}>
              <User size={20} color="white" />
            </div>
            <div>
              <div style={{ fontWeight: '600', color: 'white' }}>Profile Active: {cvProfile.full_name}</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{cvProfile.skills?.length || 0} skills parsed from CV</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '1rem' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Ready for automated applications</span>
          </div>
        </motion.div>
      )}
      
      {lastDiscovery && (
        <div style={{ marginBottom: '1rem', fontSize: '0.75rem', color: 'var(--text-secondary)', textAlign: 'right' }}>
          Local storage: <span style={{ color: 'var(--accent-color)' }}>{lastDiscovery}</span>
        </div>
      )}

      <div className="stats-grid">
        <motion.div 
          className={`stat-card ${viewMode === 'all' ? 'active' : ''}`}
          onClick={() => setViewMode('all')}
          style={{ cursor: 'pointer', border: viewMode === 'all' ? '1px solid var(--accent-color)' : '' }}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
        >
          <div className="stat-label">Total Discovered</div>
          <div className="stat-value">{summary?.total_discovered || 0}</div>
        </motion.div>
        
        <motion.div 
          className={`stat-card ${viewMode === 'unique' ? 'active' : ''}`}
          onClick={() => setViewMode('unique')}
          style={{ cursor: 'pointer', border: viewMode === 'unique' ? '1px solid var(--accent-color)' : '' }}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2 }}
        >
          <div className="stat-label">Unique Matches</div>
          <div className="stat-value" style={{ color: 'var(--success)' }}>
            {summary?.total_deduplicated || 0}
          </div>
        </motion.div>

        <motion.div 
          className="stat-card"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.3 }}
          style={{ border: '1px solid var(--success)', background: 'rgba(16, 185, 129, 0.05)' }}
        >
          <div className="stat-label">Successfully Applied</div>
          <div className="stat-value" style={{ color: 'var(--success)' }}>{tracker.applied_count}</div>
        </motion.div>

        <motion.div 
          className="stat-card"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.4 }}
          style={{ border: '1px solid #ef4444', background: 'rgba(239, 68, 68, 0.05)' }}
        >
          <div className="stat-label">Skipped / Failed</div>
          <div className="stat-value" style={{ color: '#ef4444' }}>{tracker.failed_count}</div>
        </motion.div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.5rem', fontWeight: '600' }}>Available Opportunities</h2>
        <button 
          className="btn btn-primary" 
          onClick={handleBulkApply}
          disabled={!cvProfile || !!isApplying || filteredJobs.length === 0}
          style={{ background: 'var(--accent-color)', boxShadow: '0 0 20px rgba(59, 130, 246, 0.4)' }}
        >
          <Zap size={18} fill="currentColor" /> Bulk Apply to Matches
        </button>
      </div>

      <div className="job-grid">
        <AnimatePresence>
          {filteredJobs.map((job, index) => (
            <motion.div 
              key={job.id}
              className="job-card"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ delay: index * 0.05 }}
            >
              <div className="source-badge">{job.source}</div>
              <div className="job-header">
                <div>
                  <h2 className="job-title">{job.job_title}</h2>
                  <span className="company-name">{job.company}</span>
                </div>
                {job.remote && <span className="badge">100% Remote</span>}
              </div>

              <div className="job-meta">
                <div className="job-meta-item">
                  <MapPin size={16} />
                  {job.location}
                </div>
                <div className="job-meta-item">
                  <Clock size={16} />
                  {job.posted_date}
                </div>
                {job.salary && (
                  <div className="job-meta-item" style={{ color: 'var(--success)' }}>
                    <DollarSign size={16} />
                    {job.salary}
                  </div>
                )}
                {job.applicants_count !== undefined && (
                  <div className="job-meta-item">
                    <TrendingUp size={16} />
                    {job.applicants_count} applicants
                  </div>
                )}
              </div>

              <p className="job-description">
                {job.description || "No description available."}
              </p>

              <div className="card-actions">
                <a href={job.url} target="_blank" rel="noopener noreferrer" className="btn btn-outline" style={{ border: '1px solid var(--glass-border)' }}>
                  View Posting <ExternalLink size={16} />
                </a>
                <button 
                  className={`btn ${isApplying === job.id ? 'btn-outline' : 'btn-primary'}`}
                  onClick={() => handleApply(job.id)}
                  disabled={!cvProfile || !!isApplying}
                >
                  {isApplying === job.id ? (
                    <>
                      <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}>
                        <Clock size={16} />
                      </motion.div>
                      Tailoring...
                    </>
                  ) : (
                    <>
                      Optimize & Apply <FileText size={16} />
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        <AnimatePresence>
          {showReviewOverlay && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: 'rgba(0,0,0,0.85)',
                backdropFilter: 'blur(10px)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1000,
                padding: '2rem'
              }}
            >
              <motion.div
                initial={{ scale: 0.9, y: 20 }}
                animate={{ scale: 1, y: 0 }}
                style={{
                  background: 'var(--card-bg)',
                  padding: '3rem',
                  borderRadius: '2rem',
                  maxWidth: '600px',
                  textAlign: 'center',
                  border: '1px solid var(--accent-color)',
                  boxShadow: '0 0 50px rgba(59, 130, 246, 0.3)'
                }}
              >
                <div style={{ background: 'var(--accent-color)', width: '80px', height: '80px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 2rem' }}>
                  <Globe size={40} color="white" />
                </div>
                <h2 style={{ fontSize: '2rem', marginBottom: '1rem' }}>Human Review Required</h2>
                <p style={{ color: 'var(--text-secondary)', marginBottom: '2.5rem', lineHeight: '1.6' }}>
                  The bot has opened a browser window and pre-filled the application form with your tailored CV and cover letter.
                  <br /><br />
                  <strong>Please review the form in the browser window, make any adjustments, and click "Submit" on the job site.</strong>
                </p>
                <button 
                  className="btn btn-primary" 
                  onClick={handleReviewComplete}
                  style={{ padding: '1rem 3rem', fontSize: '1.1rem', marginBottom: '1rem', width: '100%' }}
                >
                  I've Submitted. Next Job <CheckCircle size={20} />
                </button>
                <button 
                  className="btn btn-outline" 
                  onClick={() => { setShowReviewOverlay(false); setIsApplying(null); }}
                  style={{ width: '100%' }}
                >
                  Stop Automation
                </button>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {tracker.applications.length > 0 && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            style={{ marginTop: '4rem', padding: '2rem', background: 'var(--card-bg)', borderRadius: '1.5rem', border: '1px solid var(--glass-border)' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '2rem' }}>
              <History size={24} color="var(--accent-color)" />
              <h2 style={{ fontSize: '1.5rem', fontWeight: '600' }}>Recent Application History</h2>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--glass-border)', color: 'var(--text-secondary)' }}>
                    <th style={{ padding: '1rem' }}>Job Title</th>
                    <th style={{ padding: '1rem' }}>Company</th>
                    <th style={{ padding: '1rem' }}>Status</th>
                    <th style={{ padding: '1rem' }}>Reason / Notes</th>
                    <th style={{ padding: '1rem' }}>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {tracker.applications.slice().reverse().map((app: any) => (
                    <tr key={app.job_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '1rem', fontWeight: '500' }}>{app.job_title}</td>
                      <td style={{ padding: '1rem' }}>{app.company}</td>
                      <td style={{ padding: '1rem' }}>
                        <span style={{ 
                          padding: '0.25rem 0.75rem', 
                          borderRadius: '1rem', 
                          fontSize: '0.8rem',
                          background: app.status === 'success' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                          color: app.status === 'success' ? 'var(--success)' : '#ef4444'
                        }}>
                          {app.status}
                        </span>
                      </td>
                      <td style={{ padding: '1rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>{app.reason || '-'}</td>
                      <td style={{ padding: '1rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{app.timestamp}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}
        
        {!loading && filteredJobs.length === 0 && (
          <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-secondary)' }}>
            <Layout size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
            <h3>No jobs found matching your search.</h3>
          </div>
        )}
      </div>
    </div>
  );
};

export default App;
