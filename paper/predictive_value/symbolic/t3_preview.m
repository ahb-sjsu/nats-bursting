% Target 3: preview process, sigmetrics.tex l.384-436
% Sufficient statistic of the delayed history for X_t=(c_t,p_t):
%   phi = (t-Theta) mod K  (determined by the infinite past),
%   c_t revealed iff t-m == Theta (mod K)  <=> phi == mod(m,K).
% X_t: p_t = c_{t+m} if phi==0 else bottom. c_{t+m} is not in the past (t+m > t-D+m).
syms Ks positive
h2 = @(x) -x*log(x) - (1-x)*log(1-x);
allok = true;
for K = 2:6
  for D = 1:2*K
    m = D + K;
    % enumerate phi in 0..K-1, c in {0,1}, f=c_{t+m} in {0,1}, each prob 1/(4K)
    X = []; Y = [];
    for phi = 0:K-1, for c = 0:1, for f = 0:1
      if phi==0, p = f; else, p = 2; end
      if phi==mod(m,K), cy = c; else, cy = 2; end
      X(end+1) = 3*c + p;           %#ok<AGROW>
      Y(end+1) = 3*phi + cy;        %#ok<AGROW>
    end, end, end
    w = sym(1)/(4*K);
    [ux,~,ix] = unique(X); [uy,~,iy] = unique(Y);
    Pxy = sym(zeros(numel(ux), numel(uy)));
    for k = 1:numel(X), Pxy(ix(k),iy(k)) = Pxy(ix(k),iy(k)) + w; end
    Px = sum(Pxy,2); Py = sum(Pxy,1);
    MI = sym(0);
    for a = 1:numel(ux), for b = 1:numel(uy)
      if Pxy(a,b) ~= 0, MI = MI + Pxy(a,b)*log(Pxy(a,b)/(Px(a)*Py(b))); end
    end, end
    target = h2(sym(1)/K) + log(sym(2))/K;
    dI = simplify(expand(MI - target), 'Steps', 50);
    % Bayes value, Omega=1, R = 1[w=c]: static 1/2; feedback E_y max_c P(c|y)
    Pcy = sym(zeros(2, numel(uy)));
    for k = 1:numel(X), cc = floor(X(k)/3); Pcy(cc+1,iy(k)) = Pcy(cc+1,iy(k)) + w; end
    V = sum(max(Pcy,[],1)); Delta = V - sym(1)/2;
    ok = (isAlways(dI == 0)) && (Delta == sym(1)/(2*K));
    allok = allok && ok;
    if D <= 2 || mod(D,K)==0
      fprintf('T3 K=%d D=%d: MI - [h2(1/K)+ln2/K] = %s ; Delta = %s (1/(2K) = %s)\n', K, D, char(dI), char(Delta), char(sym(1)/(2*K)));
    end
  end
end
fprintf('T3 all K=2..6, D=1..2K exact match: %d\n', allok);
% general K by entropy bookkeeping (same independence structure)
HX  = log(sym(2)) + h2(1/Ks) + log(sym(2))/Ks;          % c_t, slot indicator, preview bit
HXY = (1 - 1/Ks)*log(sym(2)) + log(sym(2))/Ks;          % c_t unrevealed, preview bit unknown
fprintf('T3 general K: H(X)-H(X|Y) - [h2(1/K)+ln2/K] = %s\n', char(simplify(HX - HXY - (h2(1/Ks) + log(sym(2))/Ks))));
fprintf('T3 general K: Delta = (1/K)*1 + (1-1/K)/2 - 1/2 = %s\n', char(simplify(1/Ks + (1-1/Ks)/2 - sym(1)/2)));
