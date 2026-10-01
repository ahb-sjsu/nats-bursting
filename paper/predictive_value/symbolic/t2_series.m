% Target 2: Proposition (incomparable) (i), sigmetrics.tex l.378-383, proof l.403-404
syms r real
syms n integer
assume(r > 0 & r < 1); assume(n >= 1)
I = (1/2)*((1+r)*log(1+r) + (1-r)*log(1-r));
gen = r^(2*n)/(2*n*(2*n-1));
S = symsum(gen, n, 1, inf);
fprintf('T2 symsum r^(2n)/(2n(2n-1)) = %s\n', char(simplify(S)));
fprintf('T2 symsum - I = %s\n', char(simplify(rewrite(S - I, 'log'), 'Steps', 100)));
tI = taylor(I, r, 'Order', 41);
c = coeffs(tI, r, 'All'); c = fliplr(c);   % c(k+1) = coeff of r^k
bad = 0;
for k = 0:40
  if mod(k,2)==1 || k==0, expct = sym(0); else, expct = sym(1)/(k*(k-1)); end
  if c(k+1) ~= expct, bad = bad + 1; end
end
fprintf('T2 coefficients r^0..r^40 vs 1/(k(k-1)) for even k>=2, 0 otherwise: mismatches = %d\n', bad);
fprintf('T2 first coeffs: %s\n', char(c(1:9)));
% strictness on (0,1]: I - r^2/2 = sum_{n>=2} positive terms > 0
S2 = symsum(gen, n, 2, inf);
fprintf('T2 I - r^2/2 - sum_{n>=2} = %s\n', char(simplify(rewrite(I - r^2/2 - S2, 'log'), 'Steps', 100)));
fprintf('T2 at r=1: sqrt(I/2) = %s vs 1/2\n', char(vpa(sqrt(limit(I, r, 1, 'left')/2), 10)));
% close the log identities (valid for 0<r<1, all log arguments positive)
fprintf('T2 isAlways(symsum - I == 0) via combine: %s ; residual I-r^2/2-sum_{n>=2}: %s\n', ...
  char(simplify(combine(S - I, 'log'))), char(simplify(combine(I - r^2/2 - S2, 'log'))));
