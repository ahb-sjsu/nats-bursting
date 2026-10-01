% Target 7: Corollary (bit-limited telemetry) l.205-214; beta(D)=|r|/2 l.381, l.1083-1087
syms b positive
bst = solve(sqrt(b*log(sym(2))/2) == 1, b);
fprintf('T7 sqrt(b ln2/2)=1 at b = %s = %s\n', char(bst), char(vpa(bst, 8)));
fprintf('T7 sqrt(b ln2/2) at b=2: %s, b=3: %s\n', char(vpa(sqrt(2*log(sym(2))/2),6)), char(vpa(sqrt(3*log(sym(2))/2),6)));
% symmetric chain, flip prob p, lambda = 1-2p, r = lambda^D
syms p real
syms D positive integer
lam = 1 - 2*p;
PD = [1+lam^D, 1-lam^D; 1-lam^D, 1+lam^D]/2;
fprintf('T7 P^2 - closed form(D=2) = %s ; P^5 - closed form(D=5) = %s\n', ...
  char(simplify([1-p p; p 1-p]^2 - subs(PD, D, 2))), char(simplify([1-p p; p 1-p]^5 - subs(PD, D, 5))));
syms rr real
cond1 = [(1+rr)/2, (1-rr)/2]; cond0 = [(1-rr)/2, (1+rr)/2]; marg = [1 1]/2;
tvm1 = simplify(sum(abs(cond1 - marg))/2); tvm0 = simplify(sum(abs(cond0 - marg))/2);
tv10 = simplify(sum(abs(cond1 - cond0))/2);
fprintf('T7 TV(law X_t | X_{t-D}=1, marginal) = %s ; (=0) = %s ; beta = mean = %s\n', char(tvm1), char(tvm0), char(simplify((tvm1+tvm0)/2)));
fprintf('T7 TV between the two conditionals = %s\n', char(tv10));
% future field check: law of (X_t, X_{t+1}) given X_{t-D}=i vs marginal
syms pf real
assume(pf > 0 & pf < 1/2)
K1 = [1-pf pf; pf 1-pf];
J1 = (cond1.') .* K1; J0 = (cond0.') .* K1; JM = (marg.') .* K1;
fprintf('T7 TV on (X_t,X_{t+1}): given 1: %s ; given 0: %s\n', char(simplify(sum(abs(J1(:)-JM(:)))/2)), char(simplify(sum(abs(J0(:)-JM(:)))/2)));
