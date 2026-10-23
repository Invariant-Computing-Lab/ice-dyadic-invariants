#!/usr/bin/env python3
import json, hashlib, math, os
from pathlib import Path
import numpy as np
import pandas as pd
from numpy.linalg import qr, eigvalsh, svd, matrix_rank
from scipy.linalg import eigh
from scipy.signal import butter, sosfiltfilt, hilbert
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from sklearn.metrics import accuracy_score, r2_score
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
RES=ROOT/'results'; FIG=ROOT/'figures'
RES.mkdir(exist_ok=True); FIG.mkdir(exist_ok=True)
SEED=20260812
rng=np.random.default_rng(SEED)


def random_orthogonal(d, rng):
    Q,R=np.linalg.qr(rng.normal(size=(d,d)))
    s=np.sign(np.diag(R)); s[s==0]=1
    return Q*s

def normalize_C(C):
    n=np.linalg.norm(C,'fro')
    return C/n if n>0 else C

def power_moments(C, maxr=4, normalized=True):
    M=C@C.T
    vals=np.clip(eigvalsh(M),0,None)
    p=np.array([np.sum(vals**r) for r in range(1,maxr+1)],float)
    if normalized and p[0]>0:
        return np.array([p[r-1]/(p[0]**r) for r in range(1,maxr+1)])
    return p

def effective_rank_from_C(C):
    s=svd(C,compute_uv=False)
    w=s*s
    if w.sum()<=0:return 0.0
    p=w/w.sum(); p=p[p>1e-15]
    return float(np.exp(-np.sum(p*np.log(p))))

def canonical_corrs(X,Y):
    X=X-X.mean(0,keepdims=True); Y=Y-Y.mean(0,keepdims=True)
    n=X.shape[0]
    Sxx=(X.T@X)/(n-1); Syy=(Y.T@Y)/(n-1); Sxy=(X.T@Y)/(n-1)
    # eig whitening
    ex,U=eigh(Sxx); ey,V=eigh(Syy)
    ex=np.clip(ex,1e-10,None); ey=np.clip(ey,1e-10,None)
    Wx=U@np.diag(ex**-0.5)@U.T; Wy=V@np.diag(ey**-0.5)@V.T
    K=Wx@Sxy@Wy
    return np.sort(svd(K,compute_uv=False))[::-1]

def invertible_matrix(d,rng):
    Q1=random_orthogonal(d,rng); Q2=random_orthogonal(d,rng)
    scales=np.exp(rng.uniform(-1.0,1.0,size=d))
    return Q1@np.diag(scales)@Q2.T

def bootstrap_ci(x, rng, B=2000, alpha=.05):
    x=np.asarray(x); n=len(x)
    inds=rng.integers(0,n,size=(B,n))
    means=x[inds].mean(1)
    return np.quantile(means,[alpha/2,1-alpha/2])

def signflip_p(diffs,rng,B=4000):
    diffs=np.asarray(diffs); obs=abs(diffs.mean()); n=len(diffs)
    count=0
    for _ in range(B):
        signs=rng.choice([-1,1],size=n)
        if abs(np.mean(diffs*signs))>=obs: count+=1
    return (count+1)/(B+1)

# S1 transformation-specific invariance
rows=[]
for i in range(1000):
    C=normalize_C(rng.normal(size=(8,8)))
    f=power_moments(C,4)
    QA=random_orthogonal(8,rng); QB=random_orthogonal(8,rng)
    Cp=QA.T@C@QB; fp=power_moments(Cp,4)
    rel=np.max(np.abs(fp-f)/np.maximum(np.abs(f),1e-15))
    DA=np.diag(np.exp(rng.normal(0,.55,size=8))); DB=np.diag(np.exp(rng.normal(0,.55,size=8)))
    Cs=DA@C@DB; fs=power_moments(Cs,4)
    outrel=np.linalg.norm(np.log(np.maximum(fs,1e-15))-np.log(np.maximum(f,1e-15)))
    rows.append((i,rel,outrel))
s1=pd.DataFrame(rows,columns=['replicate','orthogonal_max_relative_error','anisotropic_log_fingerprint_distance'])
s1.to_csv(RES/'S1_transformation_invariance.csv',index=False)

# S2 restricted GL extension
rows=[]
for i in range(300):
    n=600; p=q=6; k=3
    Z=rng.normal(size=(n,k))
    Ax=rng.normal(size=(k,p)); Ay=rng.normal(size=(k,q))
    X=Z@Ax+0.8*rng.normal(size=(n,p)); Y=Z@Ay+0.8*rng.normal(size=(n,q))
    cc=canonical_corrs(X,Y)
    A=invertible_matrix(p,rng); B=invertible_matrix(q,rng)
    ccp=canonical_corrs(X@A,Y@B)
    glerr=np.max(np.abs(cc-ccp))
    C=np.cov(X.T,Y.T,bias=False)[:p,p:]
    Cp=np.cov((X@A).T,(Y@B).T,bias=False)[:p,p:]
    q2=power_moments(normalize_C(C),2)[1]; q2p=power_moments(normalize_C(Cp),2)[1]
    q2rel=abs(q2p-q2)/max(abs(q2),1e-15)
    rows.append((i,glerr,q2rel))
s2=pd.DataFrame(rows,columns=['replicate','cca_spectrum_max_abs_error','q2_relative_change'])
s2.to_csv(RES/'S2_GL_extension.csv',index=False)

# S3 moment-matched spectra and OOD classification
# Search candidates with closely matched q2 but diverse q3/q4
cand=[]
for _ in range(350000):
    lam=rng.dirichlet(np.ones(8)*1.2)
    q2=np.sum(lam**2)
    if 0.185<q2<0.187:
        cand.append((lam,q2,np.sum(lam**3),np.sum(lam**4)))
        if len(cand)>=2500: break
if len(cand)<100:
    raise RuntimeError('Not enough moment candidates')
# greedy pick diverse in q3/q4 normalized plane
arr=np.array([[c[2],c[3]] for c in cand])
# start extremes then farthest point sampling
sel=[int(np.argmin(arr[:,0])),int(np.argmax(arr[:,0]))]
while len(sel)<6:
    dists=np.min(np.linalg.norm(arr[:,None,:]-arr[np.array(sel)][None,:,:],axis=2),axis=1)
    dists[sel]=-1
    sel.append(int(np.argmax(dists)))
templates=[cand[i][0] for i in sel]
templ_df=pd.DataFrame(templates,columns=[f'lambda_{j+1}' for j in range(8)])
templ_df['q2']=[np.sum(x**2) for x in templates]; templ_df['q3']=[np.sum(x**3) for x in templates]; templ_df['q4']=[np.sum(x**4) for x in templates]
templ_df.insert(0,'class',np.arange(6)); templ_df.to_csv(RES/'S3_moment_matched_templates.csv',index=False)

Xtr_inv=[]; Xte_inv=[]; Xtr_raw=[]; Xte_raw=[]; ytr=[]; yte=[]
for cls,lam0 in enumerate(templates):
    for split,nobs in [('train',400),('test',200)]:
        for _ in range(nobs):
            lam=lam0*np.exp(rng.normal(0,0.015,size=8)); lam=np.clip(lam,1e-8,None); lam/=lam.sum()
            s=np.sqrt(lam)
            if split=='train':
                # near-canonical orientations so raw model can overfit coordinates
                QA=np.eye(8); QB=np.eye(8)
                C=QA@np.diag(s)@QB.T + rng.normal(0,0.0008,size=(8,8))
            else:
                QA=random_orthogonal(8,rng); QB=random_orthogonal(8,rng)
                C=QA@np.diag(s)@QB.T + rng.normal(0,0.0008,size=(8,8))
            C=normalize_C(C)
            pm=power_moments(C,4)
            feat=np.array([pm[1],pm[2],pm[3],effective_rank_from_C(C)])
            if split=='train': Xtr_inv.append(feat); Xtr_raw.append(C.ravel()); ytr.append(cls)
            else: Xte_inv.append(feat); Xte_raw.append(C.ravel()); yte.append(cls)
Xtr_inv=np.array(Xtr_inv);Xte_inv=np.array(Xte_inv);Xtr_raw=np.array(Xtr_raw);Xte_raw=np.array(Xte_raw);ytr=np.array(ytr);yte=np.array(yte)
feature_sets={'q2':[0],'q2_q3':[0,1],'q2_q3_q4':[0,1,2],'q2_q3_q4_erank':[0,1,2,3]}
s3scores=[]
for name,idx in feature_sets.items():
    clf=make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000,C=20))
    clf.fit(Xtr_inv[:,idx],ytr)
    s3scores.append((name,accuracy_score(ytr,clf.predict(Xtr_inv[:,idx])),accuracy_score(yte,clf.predict(Xte_inv[:,idx]))))
rawclf=make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000,C=5))
rawclf.fit(Xtr_raw,ytr)
s3scores.append(('raw_coordinates',accuracy_score(ytr,rawclf.predict(Xtr_raw)),accuracy_score(yte,rawclf.predict(Xte_raw))))
s3=pd.DataFrame(s3scores,columns=['feature_set','train_accuracy','ood_accuracy']); s3.to_csv(RES/'S3_minimal_generator_scores.csv',index=False)

# Newton identities reconstruct eigenvalues from p1..p8
def elementary_from_power(p):
    # e_0=1, k e_k=sum_{i=1}^k (-1)^(i-1)e_{k-i} p_i
    e=[1.0]
    for k in range(1,len(p)+1):
        val=sum(((-1)**(i-1))*e[k-i]*p[i-1] for i in range(1,k+1))/k
        e.append(val)
    return np.array(e[1:])
newton=[]
for i in range(300):
    lam=rng.dirichlet(np.ones(8))
    p=np.array([np.sum(lam**r) for r in range(1,9)])
    e=elementary_from_power(p)
    coeff=np.r_[1.0,[-((-1)**0)] ] if False else None
    # characteristic polynomial x^d-e1 x^(d-1)+e2... 
    coeffs=[1.0]+[((-1)**k)*e[k-1] for k in range(1,9)]
    roots=np.roots(coeffs)
    rec=np.sort(np.real_if_close(roots,tol=1000).real)
    err=np.max(np.abs(rec-np.sort(lam)))
    newton.append((i,err))
pd.DataFrame(newton,columns=['replicate','max_eigenvalue_reconstruction_error']).to_csv(RES/'S3_newton_spectrum_reconstruction.csv',index=False)

# S4 EEG-like simulation
fs=128; dur=8; ntime=fs*dur; t=np.arange(ntime)/fs; nch=6; ndyads=48
bands={'theta':(4,7),'alpha':(8,12),'beta':(13,30)}
sos={b:butter(4,[lo/(fs/2),hi/(fs/2)],btype='bandpass',output='sos') for b,(lo,hi) in bands.items()}

def colored_noise(nch,ntime,rng):
    white=rng.normal(size=(nch,ntime))
    # simple AR(1) giving low-frequency power
    x=np.empty_like(white); x[:,0]=white[:,0]
    a=.92
    for j in range(1,ntime): x[:,j]=a*x[:,j-1]+white[:,j]
    x/=x.std(axis=1,keepdims=True)
    return x

def phase_track(freq,rng,drift=.018,initial=None):
    if initial is None: initial=rng.uniform(0,2*np.pi)
    # time-varying instantaneous phase; independent tracks do not retain a constant phase difference
    return initial + 2*np.pi*freq*t + np.cumsum(rng.normal(0,drift,size=ntime))

def osc_track(phase,nch,amp,rng):
    mix=rng.normal(1,.12,size=(nch,1))
    return amp*mix*np.sin(phase[None,:])

global_theta_track=phase_track(6,rng,drift=.012)
world_data={}
for world in ['independent_null','common_input','partner_specific','mixed']:
    As=[];Bs=[]
    for d in range(ndyads):
        A=0.85*colored_noise(nch,ntime,rng); B=0.85*colored_noise(nch,ntime,rng)
        # weak independent oscillatory background with independent time-varying phase trajectories
        for f,a in [(6,.12),(10,.12),(20,.10)]:
            A+=osc_track(phase_track(f,rng),nch,a,rng); B+=osc_track(phase_track(f,rng),nch,a,rng)
        if world in ['common_input','mixed']:
            # shared across every dyad: shuffled partners should retain this component
            A+=osc_track(global_theta_track,nch,.55,rng); B+=osc_track(global_theta_track+.08,nch,.55,rng)
        if world in ['partner_specific','mixed']:
            # unique dyad-specific alpha phase trajectory: shuffled partners should break it
            shared_alpha=phase_track(10,rng,drift=.028)
            delta=rng.normal(.15,.04)
            A+=osc_track(shared_alpha,nch,.72,rng); B+=osc_track(shared_alpha+delta,nch,.72,rng)
        As.append(A);Bs.append(B)
    world_data[world]=(np.stack(As),np.stack(Bs))

def plv_matrix(A,B,sosf):
    Af=sosfiltfilt(sosf,A,axis=-1); Bf=sosfiltfilt(sosf,B,axis=-1)
    pa=np.angle(hilbert(Af,axis=-1)); pb=np.angle(hilbert(Bf,axis=-1))
    # cross-channel phase diff
    z=np.exp(1j*(pa[:,None,:]-pb[None,:,:]))
    return np.abs(z.mean(axis=-1))

metric_rows=[]; test_rows=[]
for world,(As,Bs) in world_data.items():
    perm=np.roll(np.arange(ndyads),1)
    for band,sosf in sos.items():
        reals=[]; shufs=[]; qreals=[]; qshufs=[]
        for d in range(ndyads):
            Pr=plv_matrix(As[d],Bs[d],sosf); Ps=plv_matrix(As[d],Bs[perm[d]],sosf)
            mr=Pr.mean(); ms=Ps.mean()
            qr=power_moments(normalize_C(Pr),2)[1]; qs=power_moments(normalize_C(Ps),2)[1]
            reals.append(mr);shufs.append(ms);qreals.append(qr);qshufs.append(qs)
            metric_rows.append((world,band,d,mr,ms,qr,qs))
        for metric,a,b in [('mean_plv',np.array(reals),np.array(shufs)),('q2_plv_matrix',np.array(qreals),np.array(qshufs))]:
            dif=a-b; ci=bootstrap_ci(dif,rng,1500); p=signflip_p(dif,rng,2000)
            test_rows.append((world,band,metric,a.mean(),b.mean(),dif.mean(),ci[0],ci[1],p))
pd.DataFrame(metric_rows,columns=['world','band','dyad','real_mean_plv','shuffled_mean_plv','real_q2','shuffled_q2']).to_csv(RES/'S4_dual_EEG_pairwise_metrics.csv',index=False)
s4=pd.DataFrame(test_rows,columns=['world','band','metric','real_mean','shuffled_mean','delta','ci_low','ci_high','signflip_p']);s4.to_csv(RES/'S4_dual_EEG_surrogate_tests.csv',index=False)

# S5 cross-level reconstructibility
def sample_C_from_z(z,rng,random_orientation=False):
    base=np.array([.31,.20,.14,.11,.09,.07,.05,.03])
    # z changes concentration and higher moments
    tilt=np.linspace(1.2,-1.0,8)
    lam=base*np.exp(.32*z*tilt + rng.normal(0,.035,size=8)); lam=np.clip(lam,1e-6,None); lam/=lam.sum()
    s=np.sqrt(lam)
    if random_orientation:
        QA=random_orthogonal(8,rng); QB=random_orthogonal(8,rng)
    else: QA=QB=np.eye(8)
    return normalize_C(QA@np.diag(s)@QB.T)

def invfeat(C):
    pm=power_moments(C,4); return np.array([pm[1],pm[2],pm[3],effective_rank_from_C(C)])

s5rows=[]
for world in ['linked','independent','common_cause']:
    for rep in range(15):
        ntr=600; nte=300
        ztr=rng.normal(size=ntr); zte=rng.normal(size=nte)
        Ctr=[sample_C_from_z(z,rng,False) for z in ztr]; Cte=[sample_C_from_z(z,rng,True) for z in zte]
        Ftr=np.array([invfeat(c) for c in Ctr]); Fte=np.array([invfeat(c) for c in Cte])
        Rtr=np.array([c.ravel() for c in Ctr]); Rte=np.array([c.ravel() for c in Cte])
        if world=='linked':
            # semantic target directly constructed from invariant coordinates
            def law(F): return 2.0*F[:,0]-5.0*F[:,1]+8.0*F[:,2]+0.35*F[:,3]+2.5*F[:,0]*F[:,2]
            ytr=law(Ftr)+rng.normal(0,.02,size=ntr); yte=law(Fte)+rng.normal(0,.02,size=nte)
        elif world=='independent':
            ytr=rng.normal(size=ntr); yte=rng.normal(size=nte)
        else:
            # common cause z drives both, but no imposed F->y structural law
            ytr=.55*ztr+rng.normal(0,1.0,size=ntr); yte=.55*zte+rng.normal(0,1.0,size=nte)
        invmodel=make_pipeline(StandardScaler(),PolynomialFeatures(2,include_bias=False),Ridge(alpha=1.0))
        invmodel.fit(Ftr,ytr); pinv=invmodel.predict(Fte)
        rawmodel=make_pipeline(StandardScaler(),Ridge(alpha=1000.0)); rawmodel.fit(Rtr,ytr); praw=rawmodel.predict(Rte)
        ysh=ytr.copy(); rng.shuffle(ysh)
        shmodel=make_pipeline(StandardScaler(),PolynomialFeatures(2,include_bias=False),Ridge(alpha=1.0)); shmodel.fit(Ftr,ysh); psh=shmodel.predict(Fte)
        s5rows.append((world,rep,r2_score(yte,pinv),r2_score(yte,praw),r2_score(yte,psh)))
s5=pd.DataFrame(s5rows,columns=['world','replicate','invariant_ood_r2','raw_ood_r2','trial_shuffled_r2']); s5.to_csv(RES/'S5_cross_level_reconstructibility.csv',index=False)

# S6 critical locus
rows=[]
base=np.array([1,.9,.8,.7,.6,.5,.4,.3],float)
for tt in np.r_[np.linspace(0,.9,10),.95,.98,.99,1.0]:
    for rep in range(100):
        # exact terminal rank 1; before endpoint positive tail
        tail=(1-tt)*base[1:]
        s=np.r_[1.0,tail]
        QA=random_orthogonal(8,rng); QB=random_orthogonal(8,rng)
        C=QA@np.diag(s)@QB.T
        er=effective_rank_from_C(C); mins=svd(C,compute_uv=False).min(); rank=matrix_rank(C,tol=1e-10)
        sign,logdet=np.linalg.slogdet(C@C.T)
        rows.append((tt,rep,er,mins,rank,logdet if sign>0 else -np.inf))
s6=pd.DataFrame(rows,columns=['collapse_t','replicate','effective_rank','minimum_singular_value','exact_rank','logdet_CCt']); s6.to_csv(RES/'S6_critical_locus.csv',index=False)

# figures
plt.figure(figsize=(6.8,4.3));
plt.hist(np.log10(np.maximum(s1.orthogonal_max_relative_error,1e-18)),bins=35,alpha=.75,label='Admissible O x O')
plt.axvline(np.log10(np.median(s1.anisotropic_log_fingerprint_distance)),ls='--',label='Out-of-group median (different scale)')
plt.xlabel('log10 preservation error / distance'); plt.ylabel('Count'); plt.title('Transformation-specific invariance'); plt.legend(); plt.tight_layout(); plt.savefig(FIG/'Figure_1_Transformation_Invariance.png',dpi=300); plt.close()

plt.figure(figsize=(6.8,4.3));
order=['q2','q2_q3','q2_q3_q4','q2_q3_q4_erank','raw_coordinates']
vals=[float(s3.set_index('feature_set').loc[o,'ood_accuracy']) for o in order]
plt.bar(range(len(order)),vals); plt.axhline(1/6,ls='--'); plt.ylim(0,1.05); plt.xticks(range(len(order)),['q2','q2+q3','q2+q3+q4','+ eff. rank','raw coords'],rotation=18); plt.ylabel('OOD classification accuracy'); plt.title('Minimal-generator ablation'); plt.tight_layout(); plt.savefig(FIG/'Figure_2_Minimal_Generators.png',dpi=300); plt.close()

plt.figure(figsize=(6.8,4.3));
sub=s4[(s4.metric=='mean_plv') & (((s4.world=='partner_specific')&(s4.band=='alpha'))|((s4.world=='common_input')&(s4.band=='theta')))]
labels=[]; ds=[]; los=[]; his=[]
for _,r in sub.iterrows(): labels.append(f"{r['world']}\n{r['band']}"); ds.append(r.delta); los.append(r.delta-r.ci_low); his.append(r.ci_high-r.delta)
plt.errorbar(range(len(ds)),ds,yerr=[los,his],fmt='o',capsize=5);plt.axhline(0,ls='--');plt.xticks(range(len(ds)),labels);plt.ylabel('Real - shuffled mean PLV');plt.title('Partner-shuffled surrogate controls');plt.tight_layout();plt.savefig(FIG/'Figure_3_EEG_Surrogate_Controls.png',dpi=300);plt.close()

plt.figure(figsize=(6.8,4.3));
means=s5.groupby('world')[['invariant_ood_r2','trial_shuffled_r2']].mean().reindex(['linked','independent','common_cause'])
means.index=['linked','independent','common cause']
means.columns=['Invariant fingerprint','Shuffled-label null']
means.plot(kind='bar',ax=plt.gca());plt.axhline(0,ls='--');plt.ylabel('OOD R²');plt.title('Cross-level reconstructibility and causal confound');plt.xticks(rotation=0);plt.tight_layout();plt.savefig(FIG/'Figure_4_Cross_Level_Confound.png',dpi=300);plt.close()

plt.figure(figsize=(6.8,4.3));
g=s6.groupby('collapse_t').agg(effective_rank=('effective_rank','mean'),min_s=('minimum_singular_value','mean')).reset_index();
plt.plot(g.collapse_t,g.effective_rank,marker='o',label='Effective rank'); plt.plot(g.collapse_t,g.min_s,marker='s',label='Minimum singular value');plt.xlabel('Collapse parameter t');plt.ylabel('Value');plt.title('Approach to the rank-deficient locus');plt.legend();plt.tight_layout();plt.savefig(FIG/'Figure_5_Critical_Locus.png',dpi=300);plt.close()

plt.figure(figsize=(6.8,4.3));
plt.boxplot([np.log10(np.maximum(s2.cca_spectrum_max_abs_error,1e-18)),np.log10(np.maximum(s2.q2_relative_change,1e-18))],tick_labels=['CCA spectrum error','q2 relative change']);plt.ylabel('log10 error/change');plt.title('Restricted GL extension');plt.tight_layout();plt.savefig(FIG/'Supplementary_Figure_S1_GL_Extension.png',dpi=300);plt.close()

# summary metrics
summary={
 'seed':SEED,
 'S1':{'n':len(s1),'orthogonal_max_rel_error_max':float(s1.orthogonal_max_relative_error.max()),'orthogonal_max_rel_error_median':float(s1.orthogonal_max_relative_error.median()),'anisotropic_distance_median':float(s1.anisotropic_log_fingerprint_distance.median()),'anisotropic_distance_p95':float(s1.anisotropic_log_fingerprint_distance.quantile(.95))},
 'S2':{'n':len(s2),'cca_max_abs_error_max':float(s2.cca_spectrum_max_abs_error.max()),'cca_max_abs_error_median':float(s2.cca_spectrum_max_abs_error.median()),'q2_relative_change_median':float(s2.q2_relative_change.median())},
 'S3':{'chance':1/6,'scores':{r.feature_set:{'train':float(r.train_accuracy),'ood':float(r.ood_accuracy)} for _,r in s3.iterrows()},'newton_median_max_error':float(pd.read_csv(RES/'S3_newton_spectrum_reconstruction.csv').max_eigenvalue_reconstruction_error.median()),'newton_worst_max_error':float(pd.read_csv(RES/'S3_newton_spectrum_reconstruction.csv').max_eigenvalue_reconstruction_error.max())},
 'S4':{}, 'S5':{}, 'S6':{}
}
for key,(world,band,metric) in {
 'partner_alpha_plv':('partner_specific','alpha','mean_plv'),
 'partner_alpha_q2':('partner_specific','alpha','q2_plv_matrix'),
 'common_theta_plv':('common_input','theta','mean_plv')}.items():
    r=s4[(s4.world==world)&(s4.band==band)&(s4.metric==metric)].iloc[0]
    summary['S4'][key]={k:float(r[k]) for k in ['real_mean','shuffled_mean','delta','ci_low','ci_high','signflip_p']}
for world in ['linked','independent','common_cause']:
    sub=s5[s5.world==world]
    summary['S5'][world]={c:float(sub[c].mean()) for c in ['invariant_ood_r2','raw_ood_r2','trial_shuffled_r2']}
g6=s6.groupby('collapse_t').mean(numeric_only=True)
for tt in [0.0,.95,1.0]:
    r=g6.loc[tt]
    summary['S6'][str(tt)]={'effective_rank':float(r.effective_rank),'minimum_singular_value':float(r.minimum_singular_value),'exact_rank':float(r.exact_rank),'logdet':float(r.logdet_CCt)}
(RES/'final_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')

# concise paper metrics csv
metrics=[]
def add(sec,metric,value):metrics.append((sec,metric,value))
add('S1','max O(p)xO(q) relative error',summary['S1']['orthogonal_max_rel_error_max']); add('S1','median anisotropic fingerprint distance',summary['S1']['anisotropic_distance_median'])
add('S2','max CCA spectrum GL error',summary['S2']['cca_max_abs_error_max']);add('S2','median q2 GL relative change',summary['S2']['q2_relative_change_median'])
for name,v in summary['S3']['scores'].items():add('S3',f'{name} OOD accuracy',v['ood'])
for name,v in summary['S4'].items():add('S4',f'{name} delta',v['delta']);add('S4',f'{name} p',v['signflip_p'])
for world,v in summary['S5'].items():add('S5',f'{world} invariant OOD R2',v['invariant_ood_r2'])
add('S6','effective rank t=0',summary['S6']['0.0']['effective_rank']);add('S6','effective rank t=1',summary['S6']['1.0']['effective_rank'])
pd.DataFrame(metrics,columns=['section','metric','value']).to_csv(RES/'paper_summary_metrics.csv',index=False)

print(json.dumps(summary,indent=2))
