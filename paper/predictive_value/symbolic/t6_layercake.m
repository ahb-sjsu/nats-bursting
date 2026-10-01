% Target 6: layer-cake Remark l.672-685 and appendix l.1088-1100
syms pp r lam th real
assume(pp > 0 & pp < 1); assume(r >= 0 & r <= 1); assume(lam > 0)
C = pp*(1-pp)*r;
% one layer, feedback m = xhat: goodput g = P(xhat=1,x=1), over-admission rho = P(xhat=1,x=0)
g_fb = pp^2 + C; rho_fb = pp - g_fb;
fprintf('T6 rho_fb = %s\n', char(factor(simplify(rho_fb))));
% static: admit w.p. theta -> g = theta*pi, rho = theta*(1-pi); match rho
th_m = solve(th*(1-pp) == rho_fb, th);
g_st = th_m*pp;
fprintf('T6 matched theta = %s ; static goodput = %s\n', char(simplify(th_m)), char(simplify(g_st)));
fprintf('T6 gain (pi^2+pi(1-pi)r) - pi^2(1-r) = %s\n', char(simplify(g_fb - g_st)));
% Bayes envelope (eq. 1) of the Lagrangian reward R(1,x)=1[x=1]-lam*1[x=0], R(0,x)=0
p1 = pp + C/pp; p0 = pp - C/(1-pp);
lam0 = pp/(1-pp);
fprintf('T6 kink p* = lam/(1+lam) at lam=pi/(1-pi): %s\n', char(simplify(lam0/(1+lam0))));
B0 = pp*(p1 - lam0*(1-p1));   % p1 >= p* = pi >= p0, psi(p0)=0, psi(pi)=0
fprintf('T6 Bayes envelope at lam=pi/(1-pi): %s ; minus pi*r = %s ; Omega = 1+lam = %s\n', char(simplify(B0)), char(simplify(B0 - pp*r)), char(simplify(1+lam0)));
fprintf('T6 static reward theta*(pi - lam(1-pi)) is flat in theta iff lam = %s\n', char(solve(pp - lam*(1-pp) == 0, lam)));
% counterexamples: a fixed price lam=1 (kink at 1/2), pi = 3/10
for rv = [sym(1)/10, sym(1)/2, sym(9)/10]
  pv = sym(3)/10; lv = sym(1);
  Cv = pv*(1-pv)*rv; q1 = pv + Cv/pv; q0 = pv - Cv/(1-pv);
  ps = @(x) max(sym(0), x - lv*(1-x));
  B = pv*ps(q1) + (1-pv)*ps(q0) - ps(pv);
  fprintf('T6 pi=.3, lam=1, r=%s: Bayes envelope = %s, matched-surplus gain pi*r = %s\n', char(rv), char(B), char(pv*rv));
end
for rv = [sym(1)/10, sym(1)/2]
  pv = sym(3)/10; Cv = pv*(1-pv)*rv; q1 = pv + Cv/pv; q0 = pv - Cv/(1-pv);
  ps = @(x) max(x, 1-x);
  B = pv*ps(q1) + (1-pv)*ps(q0) - ps(pv);
  fprintf('T6 pi=.3, 0/1 prediction, r=%s: Bayes envelope = %s vs pi*r = %s\n', char(rv), char(B), char(pv*rv));
end
