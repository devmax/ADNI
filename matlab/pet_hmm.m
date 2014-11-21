function [model, ll] = pet_hmm()

% read in and clean the FDG-PET scan data, and condition it to be used by
% the pmtk3 package

data_pet = '/phobos/alzheimers/adni/pet_flat.csv';

% must use this because there is some non-numeric data in table (e.g.
% VISCODE2)
data = readtable(data_pet);

% grab the DX for each patient
labels = data.DX;
nl = cellfun(@strcmp, labels, repmat({'NL'}, size(labels, 1), 1));
mci = cellfun(@strcmp, labels, repmat({'MCI'}, size(labels, 1), 1));
ad = cellfun(@strcmp, labels, repmat({'AD'}, size(labels, 1), 1));
labels = zeros(size(labels, 1), 1);
labels(nl) = 1;
labels(mci) = 2;
labels(ad) = 3;

% ignore VISCODE2 for now, which is column #2
%data = table2array(data(:, [1, 3:end]));
% the high dimensionality of the data is causing singular problems with the
% covariance matrices. Just work with means for now.
data = table2array(data(:, [1, 4:6:end]));

% divide up the data by RIDs
% RID = data(:, 1)
[~, order] = sort(data(:, 1)); % first sort based on RID
data = data(order, :); % make sure the RIDs appear in ascending order
% generate counts for each RID
counts = histc(data(:, 1), unique(data(:, 1))); 
rid = data(:, 1);

stackedData = data(:, 2:end);
stackedLabels = labels;

% counts will have the number of rows that belong to each RID
% generate a cell array now, using these counts to divide up the matrix
data = mat2cell(data(:, 2:end), counts);
labels = mat2cell(labels, counts);
% make each column an obervation rather than each row
data = cellfun(@transpose, data, 'UniformOutput', false);
labels = cellfun(@transpose, labels, 'UniformOutput', false);

dx = rowvec(sort(unique(stackedLabels)));
gt.pi = histc(stackedLabels, dx)/numel(stackedLabels);
gt.A = zeros(numel(dx));
trans = cellfun(@countTransitions, labels, ...
                repmat({dx}, numel(labels), 1), 'UniformOutput', false);
gt.A = sum(cat(3, trans{:}), 3);
gt.A = bsxfun(@rdivide, gt.A, sum(gt.A, 2));

%[model, ll] = mixGaussFit(stackedData, 5, 'verbose', true, 'maxIter', 100);
[model, ll] = hmmFit(data, 6, 'gauss', 'verbose', true, 'maxIter', 100);

end

function trans = countTransitions(labels, dx)

trans = zeros(numel(dx));
for i=1:numel(dx)
    t1 = find(labels==dx(i));
    t2 = t1 + 1;
    t2 = t2(t2 <= numel(labels));
    t1 = t1(1:numel(t2));
    if ~isempty(t1) && ~isempty(t2)
        idx = @(src, dest)sum(labels(t1)==src ...
            & labels(t2)==dest);
        trans(i, :) = arrayfun(idx, repmat(dx(i), 1, numel(dx)), dx);
    end
end

end



