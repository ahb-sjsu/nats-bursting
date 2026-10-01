% Target 4: Theorem (hinge law), sigmetrics.tex l.500-555; Fig l.557-571; Remark l.650-655; Cor l.658-666
syms pp C ps real          % pp = prior pi, ps = kink p*
assume(pp > 0 & pp < 1)
p1 = pp + C/pp;  p0 = pp - C/(1-pp);
% posteriors from the joint law of (X_{t-D}, X_t) with Cov = C
P11 = pp^2 + C; P10 = pp*(1-pp) - C; P01 = P10;
fprintf('T4 P(X=1|Y=1) - p1 = %s ; P(X=1|Y=0) - p0 = %s ; mean = %s\n', ...
  char(simplify(P11/pp - p1)), char(simplify(P01/(1-pp) - p0)), char(simplify(pp*p1 + (1-pp)*p0)));
% four branch identities for a single kink, Delta s = 1:
% Delta = pi(p1-p*)^+ + (1-pi)(p0-p*)^+ - (pi-p*)^+
e1 = simplify(pp*(p1-ps) - (C - (ps-pp)*pp));                        % C>=0, p*>=pi: only p1 can cross
e2 = simplify((1-pp)*(ps-p0) - (C - (pp-ps)*(1-pp)));                % C>=0, p*<pi : E(p*-pY)^+ via p0
e3 = simplify((1-pp)*(p0-ps) - ((-C) - (ps-pp)*(1-pp)));             % C<0,  p*>=pi: only p0 can cross
e4 = simplify(pp*(ps-p1) - ((-C) - (pp-ps)*pp));                     % C<0,  p*<pi : via p1
fprintf('T4 branch identities (should be 0 0 0 0): %s %s %s %s\n', char(e1), char(e2), char(e3), char(e4));
% exact randomized check against the DEFINITION psi(p)=max_w [p R(w,1)+(1-p) R(w,0)]
rng(7); ntrial = 400; nbad = 0; nzero = 0; nneg = 0;
hp = @(x) max(x, sym(0));
for t = 1:ntrial
  na = randi([2 5]);
  R1 = sym(randi([-20 20], na, 1))/10; R0 = sym(randi([-20 20], na, 1))/10;
  piv = sym(randi([5 95]))/100;
  psi = @(p) max(p*R1 + (1-p)*R0);
  kinks = sym([]); jumps = sym([]);
  for i = 1:na
    for j = i+1:na
      den = (R1(i)-R0(i)) - (R1(j)-R0(j));
      if den == 0, continue; end
      pk = (R0(j)-R0(i))/den;
      if pk <= 0 || pk >= 1 || any(kinks == pk), continue; end
      vals = pk*R1 + (1-pk)*R0; act = (vals == max(vals));
      sl = R1(act) - R0(act);
      if max(sl) > min(sl), kinks(end+1) = pk; jumps(end+1) = max(sl) - min(sl); end %#ok<AGROW>
    end
  end
  Cmin = -min(piv^2, (1-piv)^2); Cmax = piv*(1-piv);
  Cv = Cmin + (Cmax - Cmin)*sym(randi([0 1000]))/1000;
  if Cv < 0, nneg = nneg + 1; end
  q1 = piv + Cv/piv; q0 = piv - Cv/(1-piv);
  direct = piv*psi(q1) + (1-piv)*psi(q0) - psi(piv);
  hinge = sym(0);
  for k = 1:numel(kinks)
    pk = kinks(k);
    if Cv >= 0
      if pk >= piv, a = (pk-piv)*piv; else, a = (piv-pk)*(1-piv); end
      hinge = hinge + jumps(k)*hp(Cv - a);
    else
      if pk >= piv, a = (pk-piv)*(1-piv); else, a = (piv-pk)*piv; end
      hinge = hinge + jumps(k)*hp(-Cv - a);
    end
  end
  if direct ~= hinge, nbad = nbad + 1; end
  if direct == 0, nzero = nzero + 1; end
end
fprintf('T4 exact rational trials vs definition: %d trials (%d with C<0), %d mismatches, %d with Delta=0\n', ntrial, nneg, nbad, nzero);
% worked examples
pv = sym(35)/100; pk = sym(45)/100;
fprintf('T4 Fig: pi=.35,p*=.45: a+ = %s, a- = %s, feasible C in [%s, %s]\n', char((pk-pv)*pv), char((pk-pv)*(1-pv)), char(-pv^2), char(pv*(1-pv)));
pv = sym(2)/10; pk = sym(3)/10;
fprintf('T4 pi=.2,p*=.3: a+ = %s, a- = %s, max feasible -C = min(pi^2,(1-pi)^2) = %s\n', char((pk-pv)*pv), char((pk-pv)*(1-pv)), char(min(pv^2,(1-pv)^2)));
fprintf('T4 Remark: Delta(+0.03)/ds = %s ; Delta(-0.03)/ds = %s\n', char(hp(sym(3)/100 - (pk-pv)*pv)), char(hp(sym(3)/100 - (pk-pv)*(1-pv))));
% companion corollary: pi=1/2, psi=max(p,1-p), kink 1/2, slope jump 2, C=r/4
syms r real
psi01 = @(x) max(x, 1-x);
rv = sym(3)/10; Cv = rv/4;
D01 = psi01(sym(1)/2 + Cv*2)/2 + psi01(sym(1)/2 - Cv*2)/2 - psi01(sym(1)/2);
fprintf('T4 Cor: pi=1/2, r=0.3: Delta(0/1) direct = %s ; 2*|C| = %s ; |r|/2 = %s\n', char(D01), char(2*Cv), char(rv/2));
