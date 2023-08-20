# AMM generator

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.8266568.svg)](https://doi.org/10.5281/zenodo.8266568)

This is the artifact accompanying the paper "Mate! Are You Really Aware? An Explainability-Guided Testing Framework for Robustness of Malware Detectors", accepted by ESEC/FSE 2023.

If you would like to use this project in your research, please cite our paper:

```bib
@inproceedings{sun2023mate,
  title={Mate! {Are} You Really Aware? {An} Explainability-Guided Testing Framework for Robustness of Malware Detectors},
  author={Sun, Ruoxi and Xue, Minhui and Tyson, Gareth and Dong, Tian and Li, Shaofeng and Wang, Shuo and Zhu, Haojin and Camtepe, Seyit and Nepal, Surya},
  booktitle={Proceedings of the 30th ACM Joint European Software Engineering Conference and Symposium on the Foundations of Software Engineering},
  year={2023}
}
```

The original results are produced on a PC workstation with 64GB RAM, AMD Ryzen 3750X 8-core CPU and Linux Mint 20.1 Cinnamon installed with 256GB swap partition. We run Python 3.9.9. To reproduce the results, a machine with similar CPUs (at least 2 cores and 2.10GHz), 4 GB or larger RAM is required. Running the artifact on a different machine could possibly diverge the execution and lead to different results.  

**An example of AMM-based generation can be found in main.ipynb**

Our testing framework consists of three key components: 
1. Explainability-guided feature selection, to select the features for manipulation; 
2. A test case generator that relies on the previously selected features; and 
3. Malware detector testing to identify which detectors are robust against the adversarial malware samples. 

## Step 0: SHAP

Before diving into the testing framework, we would like to introduce preliminary knowledge about SHAP, the model explanation technique we used in our testing.

The SHAP framework subsumes several earlier model explanation techniques together, including LIME and Integrated Gradients.
SHAP has the objective of explaining the final value of a prediction by attributing a value to each feature based on its contribution to the final result. To accomplish this task, the SHAP  frameworks train a surrogate linear explanation model. Summing the effects of all feature attributions approximates the difference of prediction and the average of the original model, aiming to explain any machine learning-based model without internal knowledge.

* Step 0.1: Train a machine learning-based malware detector with a specific feature extraction (or say vectorising) method.
* Step 0.2: Applying SHAP to the trained model (examples could be found at https://github.com/shap/shap)

Considering the potential security issues, we will not release the original malware samples and generated test cases. We provide a dataset with extracted features at dataset/data.xz. An examplar code of model training could be found below.

```Python
with lzma.open('dataset/data.xz', 'rb') as file:
    raw_data = file.read()
    (x_train, x_test, y_train, y_test, feature_names) = pickle.loads(raw_data)

feature_vectorizer = CountVectorizer(
        input='filename', 
        tokenize = lambda xx: [item for item in xx.split(os.linesep) if item != ""], 
        token_pattern=None, 
        binary=True, 
        lowercase=False, 
        vocabulary=feature_names)

lgbm_model = lightgbm.Booster(model_file='./dataset/drebin_lgbm.txt')
```

## Step 1: Feature Selection (implemented in amm_generator.py)

To select the feature that has largest malicious magnitude, we propose the concept of *Accrued Malicious Magnitude (AMM)*. The AMM is defined as the product of the magnitude of SHAP values in each feature and the number of samples that have malicious-oriented values (i.e., values towards the positive side, as 1 represents malicious) in the corresponding feature. 

We select the most evasive feature according to the AMM values, denoting the dot product of the range of SHAP values and the number of SHAP values greater than mean. Please find more details of calculating AMM in our paper.

Once we have identified the feature to compromise, the next step is to choose the value for the selected feature to guide the manipulation. We select the most benign-oriented value in the feature space. This corresponds to the most negative value of the feature.

We provide a dataset with calculated SHAP value matrix in 'dataset/shap_samples_train.xz'. An examplar code of feature selction could be found below.

```Python
from amm_generator import AmmGenerator
import json

with lzma.open('dataset/shap_samples_train.xz', 'rb') as file:
    raw_data = file.read()
    (x_samples, y_samples, lgbm_shap_values) = pickle.loads(raw_data)

shap_values = lgbm_shap_values[1]

generator = AmmGenerator()
result_lgbm = generator.AMM_feature_selection(x_samples, shap_values, feature_names, trigger_size=75)

results = {key: int(result_lgbm[key]) for key in result_lgbm}

with open('amm_patch.json', 'w') as file:
    json.dump(results, file)
```

## Step 2: Test Case Generator (implemented in apk_generator.py)

After obtaining a pair of feature and value, if the selected feature is manipulable, we add the pair into a map, $P$, as the Feature Patch to be used in the feature-space manipulation. Note that, due to the strong semantic restrictions of the binaries, we cannot simply choose any arbitrary pairs of feature and values for the test manipulation. Instead, we restrict the feature-space manipulation to only features and values that are independent (IID) and can be modified with original functionalities preserved. Please find more details in our paper.

To ensure that no loss of functionality is inadvertently introduced as a side effect of feature manipulation, we only apply these changes to unreachable areas of binaries, so that these changes will never be executed during run-time. Therefore, we guarantee that test cases are executable and can be applied in the testing of malware detectors in the wild. Then, we apply these changes on seed binaries with the help of open-source binary builders. An examplar code of problem space patching (test case generating) could be found below.

```Python
import apk_generator as patcher

patcher.perform_patching('dataset/be837406e861488e43d0a374982066517c3c08cf549b2f9a1ffe252ccdf3a29b', 'amm_patch.json', '/tmp', './be837406e861488e43d0a374982066517c3c08cf549b2f9a1ffe252ccdf3a29b.pack.apk')
```

## Step 3: Malware Detector Testing

With the generated adversarial samples, we can furhter test the robustness of malware detectors. Please find detailed exmperimental results in our paper.

## Ethical considerations

Our research is concentrated on testing, which determines potential weaknesses of current malware detection methodologies. Hence, we declare: 
1. The motivating example we presented is only a code snippet without actual functionality;
2. All tools and datasets involved in our experiment are publicly available; and
3. Considering the potential security issues, we will not release the test case generator and any test cases, as well as the information of commercial antivirus involved in our evaluation, except for academic uses that are approved by our ethical committee.
