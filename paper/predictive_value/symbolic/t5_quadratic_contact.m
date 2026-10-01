% Target 5: Prop (squared error) l.562-580, Theorem (contact order) l.586-614
syms p w pp C real
assume(pp > 0 & pp < 1); assume(p >= 0 & p <= 1)
ER = -(p*(w-1)^2 + (1-p)*w^2);
wst = solve(diff(ER, w) == 0, w);
psi = simplify(subs(ER, w, wst));
fprintf('T5 argmax w = %s ; psi(p) = %s ; d2/dw2 = %s\n', char(wst), char(factor(psi)), char(diff(ER, w, 2)));
p1 = pp + C/pp; p0 = pp - C/(1-pp);
psiF = @(x) -x*(1-x);
Delta = pp*psiF(p1) + (1-pp)*psiF(p0) - psiF(pp);
VarY = pp*(p1-pp)^2 + (1-pp)*(p0-pp)^2;
fprintf('T5 Delta - Var(pY) = %s ; Delta - C^2/(pi(1-pi)) = %s\n', char(simplify(Delta - VarY)), char(simplify(Delta - C^2/(pp*(1-pp)))));
% general smooth case, tested on psi = negative entropy (log loss)
psiL = @(x) x*log(x) + (1-x)*log(1-x);
DL = pp*psiL(p1) + (1-pp)*psiL(p0) - psiL(pp);
L = limit(DL/C^2, C, 0);
target = subs(diff(psiL(p),p,2),p,pp)/(2*pp*(1-pp));
fprintf('T5 log-loss: lim Delta/C^2 = %s ; psi2(pi)/(2pi(1-pi)) = %s ; diff = %s\n', char(simplify(L)), char(simplify(target)), char(simplify(L - target)));
% contact order theorem
syms cp cm a q u positive
assume(q >= 1)
lead_pos = pp*cp*(u/pp)^q + (1-pp)*cm*(u/(1-pp))^q;   % C=u>0
fprintf('T5 C>0: lead - u^q[c+ pi^(1-q) + c- (1-pi)^(1-q)] = %s\n', char(simplify(lead_pos - u^q*(cp*pp^(1-q) + cm*(1-pp)^(1-q)), 'Steps', 50)));
lead_neg = pp*cm*(u/pp)^q + (1-pp)*cp*(u/(1-pp))^q;   % C=-u<0
fprintf('T5 C<0: lead - |C|^q[c+ (1-pi)^(1-q) + c- pi^(1-q)] = %s  (weights swapped)\n', char(simplify(lead_neg - u^q*(cp*(1-pp)^(1-q) + cm*pp^(1-q)), 'Steps', 50)));
fprintf('T5 affine part: pi*a*(u/pi) + (1-pi)*a*(-u/(1-pi)) = %s\n', char(simplify(pp*a*(u/pp) + (1-pp)*a*(-u/(1-pp)))));
fprintf('T5 q=1: lead_pos = %s ; lead_neg = %s\n', char(simplify(subs(lead_pos, q, 1))), char(simplify(subs(lead_neg, q, 1))));
syms k2 positive
fprintf('T5 q=2, c+=c-=k2/2: lead - k2 u^2/(2pi(1-pi)) = %s\n', char(simplify(subs(lead_pos, [q cp cm], [2 k2/2 k2/2]) - k2*u^2/(2*pp*(1-pp)))));
qq = sym(3)/2; pv = sym(3)/10; uu = sym(1)/50;
psiq = @(x) cp*max(x-pv,0)^qq + cm*max(pv-x,0)^qq;
Dq = pv*psiq(pv+uu/pv) + (1-pv)*psiq(pv-uu/(1-pv)) - psiq(pv);
fprintf('T5 q=3/2, pi=.3, C=.02 exact: Delta - formula = %s\n', char(simplify(Dq - uu^qq*(cp*pv^(1-qq) + cm*(1-pv)^(1-qq)))));
