% Target 1: Proposition (tightness), sigmetrics.tex l.270-298; figure l.873-878
syms r real
assume(r > -1 & r < 1)
I = (1/2)*((1+r)*log(1+r) + (1-r)*log(1-r));
% I from the joint law (1+r)/4 agree, (1-r)/4 disagree, fair marginals
P = [(1+r)/4 (1-r)/4; (1-r)/4 (1+r)/4];
MI = sym(0);
for i=1:2, for j=1:2, MI = MI + P(i,j)*log(P(i,j)/(sym(1)/4)); end, end
fprintf('T1 MI(joint law) - I = %s\n', char(simplify(expand(MI - I), 'Steps', 100)));
fprintf('T1 taylor I = %s\n', char(taylor(I, r, 'Order', 9)));
assume(r > 0 & r < 1)
ratio = sqrt(2*I)/r;      % = sqrt(I/2)/(r/2)
fprintf('T1 taylor sqrt(I/2)/(r/2) = %s\n', char(taylor(ratio, r, 'Order', 6)));
fprintf('T1 taylor (sqrt(1+r^2/6))  = %s\n', char(taylor(sqrt(1+r^2/6), r, 'Order', 6)));
fprintf('T1 taylor I/(r^2/2) = %s\n', char(taylor(I/(r^2/2), r, 'Order', 6)));
fprintf('T1 taylor gap sqrt(I/2)-r/2 = %s\n', char(taylor(sqrt(I/2) - r/2, r, 'Order', 7)));
% I >= r^2/2 on (-1,1): f = I - r^2/2, even; f(0)=0, f'(r)=atanh(r)-r, f''=r^2/(1-r^2)>=0
assume(r > -1 & r < 1)
f = I - r^2/2;
fprintf('T1 f(0) = %s\n', char(subs(f, r, 0)));
fprintf('T1 f(-r)-f(r) = %s\n', char(simplify(subs(f, r, -r) - f)));
f1 = simplify(diff(f, r));
fprintf('T1 f''(r) = %s ; f''(r)-(atanh(r)-r) = %s\n', char(f1), char(simplify(rewrite(f1 - (atanh(r) - r), 'log'))));
f2 = simplify(diff(f, r, 2));
fprintf('T1 f''''(r) = %s ; minus r^2/(1-r^2) = %s\n', char(f2), char(simplify(f2 - r^2/(1-r^2))));
xs = sym((-99:99)/100);
fv = vpa(subs(f, r, xs), 30);
fprintf('T1 min over grid r=-.99:.01:.99 of I-r^2/2 = %s (at r=0 exactly 0)\n', char(min(fv)));
% r = 1 endpoint
I1 = limit(I, r, 1, 'left');
fprintf('T1 I(1-) = %s\n', char(I1));
R1 = simplify(sqrt(I1/2)/(sym(1)/2));
fprintf('T1 sqrt(I(1)/2)/(1/2) = %s ; - sqrt(2 ln2) = %s ; vpa = %s\n', char(R1), char(simplify(R1 - sqrt(2*log(sym(2))))), char(vpa(R1, 8)));
