"""Build a classifier to make the predictions"""

import pandas as pd
import read_pet as pet
import read_mri as mri
import patient_info as pi

import numpy as np
from random import shuffle
import matplotlib.pyplot as plt

from sklearn import cross_validation, svm, linear_model
from sklearn.preprocessing import StandardScaler
from sklearn.preprocessing import LabelBinarizer
from sklearn.metrics import roc_curve, auc
from sklearn.learning_curve import validation_curve

import sys

LABELS = {'nl':1, 'mci':2, 'ad':3}

def generate_features_fdg_bl():
    """
    Generate a feature vector for each sample of the fdg data
    """
    data = pet.FDG
    # generate feature name
    data['REGION'] = data['ROINAME'] + data['ROILAT']
    # get subjects with baseline data
    dx_base, conv = pi.get_baseline_classes(data, 'ADNI1')
    features = ['MEAN', 'MEDIAN', 'MODE', 'MIN', 'MAX', 'STDEV']
    x = []
    y = []
    rid = []

    for patient in dx_base.keys():
        readings = data[(data['RID'] == patient) &
                        (data['VISCODE'] == 'bl')]
        if not readings.empty:
            assert (len(readings) == 5),\
                'More than one baseline reading for RID=%d'%patient
            patient_features = readings.pivot(index='RID',
                                              columns='REGION')\
                [features].values[0]
            x.append(patient_features)
            y.append(LABELS[dx_base[patient]])
            rid.append(patient)

    return np.array(x), np.array(y), rid

def generate_features_mri_bl():
    """
    Generate a feature vector for each patient with a baseline MRI scan
    """
    data = mri.FSX
    # use only patients with completed scans
    data = data[(data['STATUS'] == 'complete') & (data['OVERALLQC'] == 'Pass')]
    dx_base, conv = pi.get_baseline_classes(data, 'ADNI1')
    features = [col for col in data.columns
                if col[:2] == 'ST' and\
                not col == 'STATUS' and\
                ~pd.isnull(data[col]).any()]
    x = []
    y = []
    rid = []
    for patient in dx_base.keys():
        # passively reject more than one scan for the same patient
        readings = data[(data['RID'] == patient) &
                        (data['VISCODE'] == 'sc')][:1]
        if not readings.empty:
            icv = readings['ST10CV'].values.ravel()[0]
            assert (len(readings) == 1),\
                'More than one baseline reading for RID=%d'%patient
            patient_features = (readings[features]/icv).values[0]
            x.append(patient_features)
            y.append(LABELS[dx_base[patient]])
            rid.append(patient)

    return np.array(x), np.array(y), rid

def generate_features_concat():
    """
    Generate a feature vector that is the concatenation of the two modalities
    """

    data_mri = generate_features_mri_bl()
    data_fdg = generate_features_fdg_bl()
    common = list(set(data_mri[2]).intersection(data_fdg[2]))

    X = []
    Y = []

    for patient in common:
        mri_idx = data_mri[2].index(patient)
        fdg_idx = data_fdg[2].index(patient)
        X.append(np.r_[data_mri[0][mri_idx], data_fdg[0][fdg_idx]])
        assert (data_mri[1][mri_idx] == data_fdg[1][fdg_idx]), \
            'Error in corresponding labels'
        Y.append(data_fdg[1][fdg_idx])

    return np.array(X), np.array(Y)

def predict(clf, training, testing):
    """
    Apple the classifier and return predictions for training and testing data
    """
    train_acc = sum(training[1] == clf.predict(
        training[0]))*1.0/len(training[0])
    test_acc = sum(testing[1] == clf.predict(
        testing[0]))*1.0/len(testing[0])

    return (train_acc, test_acc)

def get_auc(clf, x, y, plot=False):
    """
    Keyword Arguments:
    clf -- Classifier to use
    x   -- feature matrix
    y   -- labels
    """
    prob = clf.decision_function(x)
    fpr, tpr, thresh = roc_curve(y, prob)
    auroc = auc(fpr, tpr)
    if plot:
        #plt.figure()
        generate_roc_plot(fpr, tpr, 'AUROC=%f'%auroc)
    return auroc

def generate_roc_plot(fpr, tpr, title):
    """
    Keyword Arguments:
    fpr   -- False positive rate
    tpr   -- True positive rate
    title -- Title of the plot
    """
    plt.plot([0, 1], [0, 1], 'k--')
    plt.plot(fpr, tpr)
    plt.title(title)
    plt.xlim([0., 1.])
    plt.ylim([0., 1.05])
    plt.xlabel('False positive rate')
    plt.ylabel('True positive rate')

def classify(x, y, modality):
    """
    Classify patients based on FDG-PET features
    """
    two_class = True
    classes = ['mci', 'ad']
    pos_label = LABELS['nl'] if 'nl' in classes else LABELS['mci']
    neg_label = LABELS['ad'] if 'ad' in classes else LABELS['mci']
    if two_class:
        first = [i for i in xrange(len(y)) if y[i] == LABELS[classes[0]]]
        second = [i for i in xrange(len(y)) if y[i] == LABELS[classes[1]]]
        print "Positive labels: ", len(first)
        print "Negative labels: ", len(second)
        wanted_idx = first + second
        shuffle(wanted_idx)
        x = x[wanted_idx]
        y = y[wanted_idx]

    svm_params = {}
    svm_params['verbose'] = 0
    # mri=0.002, pet=0.006
    svm_params['C'] = 0.006
    svm_params['tol'] = 1e-5
    svm_params['fit_intercept'] = True
    svm_params['loss'] = 'l1'
    clf = svm.LinearSVC(**svm_params)
    #clf = svm.SVC(verbose=0, C=10, kernel='rbf')
    #clf = linear_model.SGDClassifier(loss='log', penalty='l2',
                                     #alpha=1,
                                     #shuffle=True,
                                     #verbose=1,
                                     #fit_intercept=True)

    make_prediction = True
    plot_roc = False
    plot_val = False

    num_rep = 50
    n_folds = 5
    base = 10
    param_range = np.logspace(-5, 3, 300, base=base)

    train_acc = []
    test_acc = []
    cv_train_acc = []
    cv_test_acc = []
    aurocs_train = []
    aurocs_test = []

    #plt.figure()
    #plt.hold(True)

    for rep in xrange(num_rep):
        message = "\rRepitition %d"%(rep+1)
        sys.stdout.write(message)
        sys.stdout.flush()
        kfold = cross_validation.KFold(len(x), n_folds=n_folds, shuffle=True)
        fold_train_acc = []
        fold_test_acc = []
        fold_cv_train_acc = []
        fold_cv_test_acc = []
        idx = 0
        for train_idx, test_idx in kfold:
            idx += 1
            sys.stdout.write(message+": Fold %d..."%idx)
            sys.stdout.flush()

            # pre-process and clean data
            scaler = StandardScaler(with_mean=True,
                                    with_std=True).fit(x[train_idx])
            binarizer = LabelBinarizer().fit(y[train_idx])
            x = scaler.transform(x)
            y = binarizer.transform(y).ravel()

            x_train, x_test = x[train_idx], x[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            if make_prediction:
                clf = svm.LinearSVC(**svm_params)
                clf.fit(x_train, y_train)
                aurocs_test.append(
                    get_auc(clf, x_test, y_test, plot=plot_roc))
                aurocs_train.append(
                    get_auc(clf, x_train, y_train, plot=False))
                accuracy = predict(clf, (x_train, y_train), (x_test, y_test))
                fold_train_acc.append(accuracy[0])
                fold_test_acc.append(accuracy[1])
            if plot_val:
                train_scores, test_scores = validation_curve(clf,
                                                             x_train, y_train,
                                                             param_name="C",
                                                             param_range=\
                                                             param_range,
                                                             cv=n_folds,
                                                             scoring="roc_auc")
                                                             #scoring="accuracy")
                # take average accross inner folds
                fold_cv_train_acc.append(np.mean(train_scores, axis=1))
                fold_cv_test_acc.append(np.mean(test_scores, axis=1))

        # now take average accross outer folds
        cv_train_acc.append(np.array(fold_cv_train_acc).mean(axis=0))
        cv_test_acc.append(np.array(fold_cv_test_acc).mean(axis=0))
        # keep accuracy for each fold so we can see variance
        train_acc.append(np.array(fold_train_acc))
        test_acc.append(np.array(fold_test_acc))

    train_acc = np.array(train_acc)
    test_acc = np.array(test_acc)
    cv_train_acc = np.array(cv_train_acc)
    cv_test_acc = np.array(cv_test_acc)

    #plt.hold(False)
    if make_prediction:
        plt.figure()
        plt.title(modality+": Classification accuracy of SVM")
        plt.xlabel("Repitition number")
        plt.ylabel("Classification accuracy")
        plt.ylim(0.0, 1.1)
        plt.xlim(0, num_rep+2)
        plt.plot(range(1, num_rep+1), train_acc.mean(axis=1),
                 label="Training Accuracy", color='r')
        plt.fill_between(range(1, num_rep+1),
                         train_acc.mean(axis=1) - train_acc.std(axis=1),
                         train_acc.mean(axis=1) + train_acc.std(axis=1),
                         alpha=0.2, color='r')
        plt.plot(range(1, num_rep+1), test_acc.mean(axis=1),
                 label="Testing Accuracy", color='g')
        plt.fill_between(range(1, num_rep+1),
                         test_acc.mean(axis=1) - test_acc.std(axis=1),
                         test_acc.mean(axis=1) + test_acc.std(axis=1),
                         alpha=0.2, color='g')
        plt.legend(loc="best")

    if plot_val:
        plt.figure()
        plt.title(modality+": Validation curve for parameter selection")
        plt.xlabel("C")
        plt.ylabel("Score")
        plt.ylim(0.0, 1.1)
        plt.semilogx(param_range, cv_train_acc.mean(axis=0),
                     basex=base,
                     label="Training score", color="r")
        plt.fill_between(param_range,
                         cv_train_acc.mean(axis=0) - cv_train_acc.std(axis=0),
                         cv_train_acc.mean(axis=0) + cv_train_acc.std(axis=0),
                         alpha=0.2, color="r")
        plt.semilogx(param_range, cv_test_acc.mean(axis=0),
                     basex=base,
                     label="Testing score", color="g")
        plt.fill_between(param_range,
                         cv_test_acc.mean(axis=0) - cv_test_acc.std(axis=0),
                         cv_test_acc.mean(axis=0) + cv_test_acc.std(axis=0),
                         alpha=0.2, color="g")
        plt.legend(loc="best")

def main():
    """
    Main function
    """
    DO_MRI = False
    DO_PET = True
    CONCAT = False

    if DO_PET:
        PET_X, PET_Y, _ = generate_features_fdg_bl()
        print "\nClassifying PET data..."
        classify(PET_X, PET_Y, "PET")

    if DO_MRI:
        MRI_X, MRI_Y, _ = generate_features_mri_bl()
        print "\nClassifying MRI data..."
        classify(MRI_X, MRI_Y, "MRI")

    if CONCAT:
        X, Y = generate_features_concat()
        print "\nClassifying concatenated data..."
        classify(X, Y, "CONCAT")

    plt.show()

if __name__ == '__main__':
    main()
