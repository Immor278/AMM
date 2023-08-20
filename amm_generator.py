import numpy
from scipy.sparse import csr_matrix

class AmmGenerator:

    def AMM_feature_selection(self, x_dataset_matrix: csr_matrix, s_matrix_shap: numpy.ndarray, feature_names: list, trigger_size=75):

        if type(x_dataset_matrix) is csr_matrix:
            x_local = x_dataset_matrix.toarray()
        else:
            x_local = x_dataset_matrix

        shap_matrix_t = s_matrix_shap.T
        distances_feature = numpy.array([item.max() - item.min() for item in shap_matrix_t])

        feature_count = shap_matrix_t.shape[0]
        sample_count = x_local.shape[0]

        d_p = []

        for index in range(0, feature_count):
            distance = distances_feature[index]
            shap_vec = shap_matrix_t[index]
            mean = numpy.mean(shap_vec)
            p = numpy.sum(shap_vec > mean) / sample_count  # find vi > mean
            d_p.append(distance * p)

        order_feature = numpy.argsort(-numpy.array(d_p))
        output = {}
        for _index in range(0, trigger_size):
            order = order_feature[_index]
            feature = feature_names[order]
            shap_vec = shap_matrix_t[order]
            row = numpy.argmin(shap_vec)
            value = x_local[row][order]
            output[feature] = value

        return output

    def statistics_feature_selection(self, x, y, feature_names, select_num=300):
        dimension = x.shape[1]
        x_ben = []
        x_mal = []
        for index in range(len(y)):
            value = y[index]
            if value == 0:
                x_ben.append(x[index])
            else:
                x_mal.append(x[index])

        x_benign = numpy.array(x_ben)
        x_malicious = numpy.array(x_mal)
        bens_sum = x_benign.sum(axis=0).toarray()[0].tolist()
        mal_sum = x_malicious.sum(axis=0).toarray()[0].tolist()

        mal_top = mal_sum.copy()
        mal_top.sort(reverse=True)
        mal_top_2 = [item for item in mal_top if item > 0]
        border_mal_top = mal_top_2[int(len(mal_top_2) * 0.1)]
        border_mal_bottom = mal_top_2[int(len(mal_top_2) * 0.9)]

        ben_top = bens_sum.copy()
        ben_top.sort(reverse=True)
        ben_top_2 = [item for item in ben_top if item > 0]
        border_ben_top = ben_top_2[int(len(ben_top_2) * 0.1)]
        border_ben_bottom = ben_top_2[int(len(ben_top_2) * 0.9)]

        mal_indexes = []
        ben_indexes = []
        for index in range(dimension):
            ben_int = bens_sum[index]
            mal_int = mal_sum[index]
            if ben_int >= border_ben_top and mal_int <= border_mal_bottom:
                ben_indexes.append(index)
            elif mal_int >= border_mal_top and ben_int <= border_ben_bottom:
                mal_indexes.append(index)

        mal_top_map = {value: mal_sum[value] for value in mal_indexes}
        mal_top_map = dict(sorted(mal_top_map.items(), key=lambda item: item[1], reverse=True))
        mal_top_fts = [key for key in mal_top_map][:select_num]

        ben_top_map = {value: bens_sum[value] for value in ben_indexes}
        ben_top_map = dict(sorted(ben_top_map.items(), key=lambda item: item[1], reverse=True))
        ben_top_fts = [key for key in ben_top_map][:select_num]

        mal_names = [feature_names[index] for index in mal_top_fts]
        ben_names = [feature_names[index] for index in ben_top_fts]
        return mal_names, ben_names