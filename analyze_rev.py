import csv
def num(x):
    try: return float(x)
    except: return 0.0
months=['202604','202605','202606','202607','202608']
def share_of(rp):
    if '词50%' in rp and '100%' not in rp: return 0.5
    if '100%' in rp: return 1.0
    return 0.5

# 1) 月度概览（汽水音乐平台）
print("==== 月度概览（汽水音乐平台）====")
print(f"{'月份':<8}{'免费播放':>12}{'付费播放':>12}{'总播放':>12}{'付费占比':>9}{'分成(元)':>10}{'RPM元/千次':>12}")
monthly={}
for p in months:
    rows=list(csv.DictReader(open(f'结算明细/结算明细_{p}.csv',encoding='utf-8')))
    ff=fp=pl=sr=0.0
    for r in rows:
        if r['平台']!='汽水音乐': continue
        f=num(r['免费播放量']); pa=num(r['付费播放量']); s=num(r['分成收入'])
        ff+=f; fp+=pa; pl+=f+pa; sr+=s
    ps = fp/pl*100 if pl else 0
    rpm = sr/pl*1000 if pl else 0
    monthly[p]=(ff,fp,pl,sr,ps,rpm)
    print(f"{p:<8}{ff:>12.0f}{fp:>12.0f}{pl:>12.0f}{ps:>8.1f}%{sr:>10.2f}{rpm:>12.3f}")

# 2) 全局：把 分成收入 按 share 归一化后回归 base = rf*free + rp*paid
print("\n==== 收入公式拆解（share 归一化全局回归）====")
Sx1=Sx2=Sx1x1=Sx1x2=Sx2x2=Sx1y=Sx2y=0.0; n=0
for p in months:
    for r in csv.DictReader(open(f'结算明细/结算明细_{p}.csv',encoding='utf-8')):
        if r['平台']!='汽水音乐': continue
        f=num(r['免费播放量']); pa=num(r['付费播放量']); s=num(r['分成收入'])
        if (f+pa)>0 and s>0:
            sh=share_of(r['权利比例']); base=s/sh
            Sx1+=f;Sx2+=pa;Sx1x1+=f*f;Sx1x2+=f*pa;Sx2x2+=pa*pa;Sx1y+=f*base;Sx2y+=pa*base; n+=1
det=Sx1x1*Sx2x2-Sx1x2*Sx1x2
rf=(Sx1y*Sx2x2-Sx2y*Sx1x2)/det; rp=(Sx1x1*Sx2y-Sx1x2*Sx1y)/det
print(f"样本={n}")
print(f"基础单价(每播放): 免费 rf={rf:.8f}  付费 rp={rp:.8f}")
print(f"  => 每千次: 免费 {rf*1000:.4f}元, 付费 {rp*1000:.4f}元  (付费≈免费{(rp/rf) if rf else 0:.1f}倍)")
print(f"分成收入 = 权利比例 share × (免费播放×{rf:.6f} + 付费播放×{rp:.6f})")
print(f"  其中 share: 词50%→0.5, 100%→1.0")

# 3) 逐月·每组 基础单价（按组回归），看是否下滑
print("\n==== 逐月基础单价（分 权利比例 组，修正行列式）====")
print(f"{'月份':<8}{'组':<6}{'播放':>12}{'组RPM':>10}{'rf(千次免费)':>14}{'rp(千次付费)':>14}")
for p in months:
    rows=list(csv.DictReader(open(f'结算明细/结算明细_{p}.csv',encoding='utf-8')))
    for lab,sh in [('50%',0.5),('100%',1.0)]:
        qs=[(num(r['免费播放量']),num(r['付费播放量']),num(r['分成收入'])) for r in rows if r['平台']=='汽水音乐' and (num(r['免费播放量'])+num(r['付费播放量']))>0 and num(r['分成收入'])>0 and share_of(r['权利比例'])==sh]
        if not qs: continue
        A,B,S1=Sx1x1,Sx1x2,Sx2x2
        a1=a2=b1=b2=0.0
        for f,pa,s in qs:
            a1+=f*f; a2+=f*pa; b1+=pa*pa; S1+=0
        # recompute per group
        X1=X2=XX11=XX12=XX22=XY1=XY2=0.0
        for f,pa,s in qs:
            X1+=f;X2+=pa;XX11+=f*f;XX12+=f*pa;XX22+=pa*pa;XY1+=f*s;XY2+=pa*s
        dd=XX11*XX22-XX12*XX12
        if abs(dd)>1e-12:
            af=(XY1*XX22-XY2*XX12)/dd; ap=(XX11*XY2-XX12*XY1)/dd
        else: af=ap=float('nan')
        pl=sum(f+pa for f,pa,s in qs); sr=sum(s for f,pa,s in qs)
        print(f"{p:<8}{lab:<6}{pl:>12.0f}{sr/pl*1000:>10.3f}{af*1000:>14.4f}{ap*1000:>14.4f}")
PY