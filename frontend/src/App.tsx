import React, { useEffect, useState } from 'react';
import axios from 'axios';
import brandMark from './assets/brand-mark.svg';
import { 
  MapPin, Clock, ExternalLink, Search, CheckCircle, 
  Loader2, Play, Upload, ChevronRight,
  SkipForward, FileText 
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

interface Job {
  id: string; source: string; job_title: string; company: string;
  location: string; remote: boolean; posted_date: string; url: string;
  description: string; status: string; salary?: string;
}

interface Stats {
  total_discovered: number; applied_count: number; remaining_count: number;
  by_status: Record<string, number>;
}

interface Summary {
  total_discovered: number; total_deduplicated: number;
  by_source: Record<string, number>;
}

interface AppStatus {
  running: boolean; current_job?: { title: string; company: string; id?: string };
  current_idx?: number; total?: number; error?: string;
}

interface DiscoveryLogs {
  lines: string[];
}

const App: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [allJobs, setAllJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [appStatus, setAppStatus] = useState<AppStatus>({ running: false });
  const [discoveryRunning, setDiscoveryRunning] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [profile, setProfile] = useState<any>(null);
  const [tailoredPreview, setTailoredPreview] = useState<any>(null);
  const [discoveryLogs, setDiscoveryLogs] = useState<string[]>([]);
  const [discoveryMessage, setDiscoveryMessage] = useState<string>('');

  const [selectedPreviewJobId, setSelectedPreviewJobId] = useState<string | null>(null);
  const [isGeneratingPreview, setIsGeneratingPreview] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'jobs' | 'cv'>('overview');
  const [overviewMode, setOverviewMode] = useState<'all' | 'unique'>('unique');
  const [postSubmitPrompt, setPostSubmitPrompt] = useState(false);

  const fetchData = async () => {
    try {
      const [uniqueJobsRes, allJobsRes, statsRes, profileRes, discoveryStatusRes, appStatusRes, summaryRes] = await Promise.all([
        axios.get(`${API_BASE}/jobs?mode=unique`),
        axios.get(`${API_BASE}/jobs?mode=all`),
        axios.get(`${API_BASE}/stats`),
        axios.get(`${API_BASE}/cv/profile`),
        axios.get(`${API_BASE}/discover/status`),
        axios.get(`${API_BASE}/apply/status`),
        axios.get(`${API_BASE}/summary`)
      ]);
      const logsRes = await axios.get<DiscoveryLogs>(`${API_BASE}/discover/logs?limit=18`);
      setJobs(uniqueJobsRes.data);
      setAllJobs(allJobsRes.data);
      setStats(statsRes.data);
      setProfile(profileRes.data);
      setDiscoveryRunning(discoveryStatusRes.data.running);
      setDiscoveryMessage(discoveryStatusRes.data.last_message || '');
      setDiscoveryLogs(logsRes.data.lines || []);
      setAppStatus(appStatusRes.data);
      setSummary(summaryRes.data);

      // If automated loop is running, fetch the current active job's tailored preview
      if (appStatusRes.data.running && appStatusRes.data.current_job) {
        const currentJob = uniqueJobsRes.data.find((j: any) => 
          j.job_title === appStatusRes.data.current_job.title && 
          j.company === appStatusRes.data.current_job.company
        );
        if (currentJob) {
          try {
            const tailoredRes = await axios.get(`${API_BASE}/jobs/tailored/${currentJob.id}`);
            setTailoredPreview(tailoredRes.data);
          } catch (e) {
            setTailoredPreview(null);
          }
        }
      } else if (!selectedPreviewJobId) {
        // Only clear preview if not running AND no manual preview is selected
        setTailoredPreview(null);
      }
    } catch (error) {
      console.error('Failed to fetch data:', error);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [selectedPreviewJobId, activeTab]);

  const handleStartDiscovery = async () => {
    setDiscoveryRunning(true);
    try {
      await axios.post(`${API_BASE}/discover`);
      fetchData();
    } catch (error) {
      console.error(error);
    }
  };

  const handleApplyNow = async (jobId: string) => {
    setActiveTab('cv'); // Switch to CV view so they can see the magic happening
    setSelectedPreviewJobId(jobId);
    setTailoredPreview(null);
    setPostSubmitPrompt(false);
    
    // Automatically trigger preview first (for visual effect) and then start the apply flow
    setIsGeneratingPreview(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });

    try {
      // 1. Trigger the single job apply in the backend
      await axios.post(`${API_BASE}/apply/start`, [jobId]);
      fetchData();
    } catch (error) { 
      console.error(error); 
      alert('Failed to start application. Ensure backend is running.');
      setIsGeneratingPreview(false);
    }
  };

  const handleReviewComplete = async () => {
    try { 
      await axios.post(`${API_BASE}/apply/review/complete`); 
      setPostSubmitPrompt(true);
    } catch (error) { console.error(error); }
  };

  const handleSkipApplication = async () => {
    try { 
      await axios.post(`${API_BASE}/apply/skip`); 
      setPostSubmitPrompt(true);
    } catch (error) { console.error(error); }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.[0]) return;
    const formData = new FormData();
    formData.append('file', e.target.files[0]);
    try {
      await axios.post(`${API_BASE}/cv/upload`, formData);
      fetchData();
    } catch (error) {
      alert('Failed to upload CV');
    }
  };

  const filteredJobs = jobs.filter(job => 
    job.job_title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    job.company.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const readyToApplyJobs = filteredJobs.filter(job =>
    job.status === 'tailored' || job.status === 'ready'
  );

  const overviewJobs = (overviewMode === 'all' ? allJobs : jobs).filter(job => 
    job.job_title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    job.company.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const scanButtonLabel = discoveryRunning ? 'Scanning Jobs' : 'Scan Jobs';

  const renderJobCard = (job: Job, index: number, showApplyButton: boolean) => (
    <motion.div
      key={job.id}
      className={`job-card-v2 status-${job.status}`}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay: index * 0.03 }}
    >
      <div className="card-top">
        <span className="source-tag">{job.source}</span>
        <span className={`status-tag ${job.status}`}>{job.status}</span>
      </div>
      <div className="card-body">
        <h4 className="job-title">{job.job_title}</h4>
        <p className="company-name">{job.company}</p>
        <div className="meta-info">
          <span><MapPin size={14} /> {job.location}</span>
          <span><Clock size={14} /> {job.posted_date}</span>
        </div>
      </div>
      <div className="card-footer">
        <div className="flex gap-2">
          <a href={job.url} target="_blank" rel="noopener noreferrer" className="icon-btn"><ExternalLink size={18} /></a>
        </div>
        {showApplyButton && profile && (
          <button
            className="btn btn-primary btn-small"
            onClick={() => handleApplyNow(job.id)}
            disabled={isGeneratingPreview || appStatus.running}
          >
            <Play size={14} /> Apply Now
          </button>
        )}
      </div>
    </motion.div>
  );

  return (
    <div className="app-container">
      <header className="main-header">
        <div className="logo-section">
          <motion.div className="logo-icon" animate={{ rotate: 360 }} transition={{ duration: 20, repeat: Infinity, ease: "linear" }}>
            <img src={brandMark} alt="" aria-hidden="true" />
          </motion.div>
          <div>
            <h1>Job Bot <span className="text-gradient">Pro</span></h1>
            <p>Automated Data Engineering Career Agent</p>
          </div>
        </div>

        <div className="header-actions">
          <div className="search-bar">
            <Search size={18} />
            <input type="text" placeholder="Filter roles..." value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
          </div>
          <button className={`btn btn-primary ${discoveryRunning ? 'loading' : ''}`} onClick={handleStartDiscovery} disabled={discoveryRunning}>
            {discoveryRunning ? <Loader2 className="spin" /> : <Play size={18} />}
            {scanButtonLabel}
          </button>
        </div>
      </header>

      {(discoveryRunning || discoveryLogs.length > 0) && (
        <section className={`scan-status-panel ${discoveryRunning ? 'active' : ''}`}>
          <div className="scan-status-header">
            <div>
              <h3>{discoveryRunning ? 'Discovery running' : 'Last discovery run'}</h3>
              <p>{discoveryMessage || (discoveryRunning ? 'Fetching jobs from Apify actors.' : 'No active scan.')}</p>
            </div>
            <span className={`scan-status-pill ${discoveryRunning ? 'live' : 'idle'}`}>
              {discoveryRunning ? 'Live' : 'Idle'}
            </span>
          </div>
          {discoveryLogs.length > 0 && (
            <div className="scan-log-window">
              {discoveryLogs.map((line, index) => (
                <div key={`${index}-${line}`} className="scan-log-line">{line}</div>
              ))}
            </div>
          )}
        </section>
      )}

      <nav className="tab-navigation">
        <button className={`tab-item ${activeTab === 'overview' ? 'active' : ''}`} onClick={() => setActiveTab('overview')}>Overview</button>
        <button className={`tab-item ${activeTab === 'jobs' ? 'active' : ''}`} onClick={() => setActiveTab('jobs')}>Apply for Jobs</button>
        <button className={`tab-item ${activeTab === 'cv' ? 'active' : ''}`} onClick={() => setActiveTab('cv')}>Upload CV</button>
      </nav>

      <div className="app-content-wrapper">
        {activeTab === 'overview' && (
          <div className="tab-pane overview-pane">
            <h2 className="mb-4">System Overview</h2>
            <div className="metrics-grid">
              <div
                className={`stat-card cursor-pointer ${overviewMode === 'all' ? 'active-all' : ''}`}
                onClick={() => setOverviewMode('all')}
              >
                <div className="stat-label">Total Discovered</div>
                <div className="stat-value">{summary?.total_discovered || 0}</div>
                <div className="source-breakdown mt-2 text-sm text-muted">
                  <div className="flex justify-between"><span>LinkedIn:</span> <span>{summary?.by_source?.LinkedIn || summary?.by_source?.linkedin || 0}</span></div>
                  <div className="flex justify-between"><span>Indeed:</span> <span>{summary?.by_source?.Indeed || summary?.by_source?.indeed || 0}</span></div>
                </div>
              </div>
              
              <div
                className={`stat-card border-success-subtle cursor-pointer ${overviewMode === 'unique' ? 'active-unique' : ''}`}
                onClick={() => setOverviewMode('unique')}
              >
                <div className="stat-label">Unique Jobs</div>
                <div className="stat-value text-success">{summary?.total_deduplicated || 0}</div>
                <div className="source-breakdown mt-2 text-sm text-muted">
                  <p>Duplicates automatically removed</p>
                </div>
              </div>

              <div className="stat-card border-warning-subtle">
                <div className="stat-label">Ready to Apply</div>
                <div className="stat-value text-warning">{stats?.remaining_count || 0}</div>
                <div className="source-breakdown mt-2 text-sm text-muted">
                  <p>Ready to apply</p>
                </div>
              </div>
            </div>

            <div className="overview-jobs-section">
              <div className="overview-jobs-header">
                <div>
                  <h3>{overviewMode === 'all' ? 'All Discovered Jobs' : 'Unique Jobs'}</h3>
                  <p>
                    {overviewMode === 'all'
                      ? 'Showing every discovered role from the latest scan.'
                      : 'Showing the deduplicated set after duplicate removal.'}
                  </p>
                </div>
                <span className="badge badge-warning">
                  {overviewJobs.length} Jobs
                </span>
              </div>

              <div className="job-cards-grid overview-job-grid">
                <AnimatePresence>
                  {overviewJobs.filter(j => j.status !== 'submitted').map((job, index) => renderJobCard(job, index, true))}
                </AnimatePresence>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'jobs' && (
          <div className="tab-pane jobs-pane">
            <div className="job-list-container">
              <div className="list-header">
                <h3>Jobs Ready for Application</h3>
                <span className="badge badge-warning">
                  {readyToApplyJobs.length} Ready
                </span>
              </div>
              <div className="job-cards-grid">
                {readyToApplyJobs.length > 0 ? (
                  <AnimatePresence>
                    {readyToApplyJobs.map((job, index) => renderJobCard(job, index, true))}
                  </AnimatePresence>
                ) : (
                  <div className="empty-state">
                    <p>No jobs are ready yet. Start from the Overview tab to tailor a job, then it will appear here.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'cv' && (
          <div className="tab-pane cv-pane">
            <div className="upload-section mb-4">
               <div className="stat-card stat-card-accent text-center">
                  <h4 className="mb-2">Document Center</h4>
                  <p className="text-sm text-muted mb-4">Upload your latest CV to start the automated workflow.</p>
                  <label className="btn btn-primary w-full justify-center cursor-pointer">
                    <Upload size={18} />
                    {profile?.full_name ? 'Update CV' : 'Upload CV'}
                    <input type="file" hidden onChange={handleFileUpload} />
                  </label>
               </div>
            </div>

            <div className="cv-intelligence-window">
              <div className="section-header">
                <h3 className="section-title">
                  <FileText size={20} /> CV Intelligence & Workflow
                </h3>
                {selectedPreviewJobId && !appStatus.running && !postSubmitPrompt && (
                  <button 
                    className="btn-small btn-outline" 
                    onClick={() => { setSelectedPreviewJobId(null); setTailoredPreview(null); }}
                  >
                    Return to Profile View
                  </button>
                )}
              </div>
              
              {!profile && !appStatus.running && !selectedPreviewJobId && (
                 <div className="empty-state">
                   <p>No CV uploaded. Please upload your CV from the Document Center above to begin.</p>
                 </div>
              )}

              {/* Post-Submit Prompt */}
              {postSubmitPrompt && !appStatus.running && (
                <div className="review-banner active mb-4">
                  <div className="flex items-center gap-3">
                    <CheckCircle className="text-success" size={24} />
                    <div>
                      <strong className="text-success">Application Completed!</strong>
                      <p>Would you like to apply to another job?</p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button className="btn btn-primary" onClick={() => { setPostSubmitPrompt(false); setActiveTab('jobs'); }}>Yes, take me to jobs</button>
                    <button className="btn btn-outline" onClick={() => { setPostSubmitPrompt(false); }}>No, dismiss</button>
                  </div>
                </div>
              )}

              {/* Parallel View: Original vs Parsed */}
              {profile && !appStatus.running && !selectedPreviewJobId && (
                <div className="parallel-view">
                  <div className="view-card">
                    <h4>Original Document</h4>
                    <iframe src={`${API_BASE}/cv/file`} className="cv-iframe" title="Original CV" />
                  </div>
                  <div className="view-card">
                    <h4>Parsed Intelligence</h4>
                    <div className="parsed-data">
                      <div className="data-group"><label>Full Name</label><div>{profile.full_name}</div></div>
                      <div className="data-group"><label>Summary</label><p>{profile.summary}</p></div>
                      <div className="data-group"><label>Key Skills</label><div className="tag-cloud">{profile.skills?.map((s: string) => <span key={s} className="badge">{s}</span>)}</div></div>
                      <div className="data-group">
                        <label>Experience</label>
                        <div className="exp-list">{profile.experience?.map((e: any, i: number) => <div key={i} className="exp-item"><strong>{e.role}</strong> @ {e.company}</div>)}</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Workflow & Preview View */}
              {(appStatus.running || selectedPreviewJobId) && (
                <div className="workflow-container">
                  {appStatus.running && (
                    <div className="review-banner active">
                      <div className="flex items-center gap-4">
                        <div className="progress-circle">
                          <span className="text-xs font-bold">{appStatus.current_idx}/{appStatus.total}</span>
                        </div>
                        <div>
                          <strong>Active Application: {appStatus.current_job?.title}</strong>
                          <p>Processing at {appStatus.current_job?.company}. Reviewing ATS assets...</p>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button className="btn btn-outline text-danger border-danger" onClick={handleSkipApplication}><SkipForward size={18} /> Skip</button>
                        <button className="btn btn-success" onClick={handleReviewComplete}>Submit Done <ChevronRight size={18} /></button>
                      </div>
                    </div>
                  )}
                  
                  {isGeneratingPreview && !appStatus.running && (
                    <div className="preview-loading">
                      <Loader2 className="spin text-primary mb-4" size={40} />
                      <h4>Analyzing Job Description...</h4>
                      <p className="text-muted">Tailoring your ATS CV and Cover Letter for this specific role.</p>
                    </div>
                  )}

                  <AnimatePresence>
                    {tailoredPreview && !isGeneratingPreview && (
                      <motion.div className="tailoring-preview" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
                        {!appStatus.running && selectedPreviewJobId && (
                           <div className="success-note">
                              <strong className="text-success">Preview Generated Successfully!</strong>
                              <p className="text-sm">These assets are customized for this role using your uploaded profile.</p>
                           </div>
                        )}
                        <div className="preview-grid">
                          <div className="preview-pane">
                            <div className="pane-header"><FileText size={16} /> Tailored ATS CV</div>
                            <div className="ats-cv-content">
                              <h5>{tailoredPreview.cv?.full_name}</h5>
                              <p className="ats-summary">{tailoredPreview.cv?.summary}</p>
                              <h6>Professional Experience</h6>
                              {tailoredPreview.cv?.experience?.map((e: any, i: number) => (
                                <div key={i} className="ats-item">
                                  <strong>{e.role} | {e.company}</strong>
                                  <p>{e.description}</p>
                                </div>
                              ))}
                            </div>
                          </div>
                          <div className="preview-pane">
                            <div className="pane-header"><FileText size={16} /> Cover Letter</div>
                            <div className="cover-letter-content">
                              <pre>{tailoredPreview.cover_letter}</pre>
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default App;
