__all__ = ["CartAndLDA"]

import recipe.i6_asr.cart as cart
import recipe.i6_asr.features as features
import recipe.i6_asr.lda as lda
import recipe.i6_asr.mm as mm
import recipe.i6_asr.rasr as rasr


class CartAndLDA:
    default_eigenvalue_params = {"verification_tolerance": 1e13}
    default_generalized_eigenvalue_params = {
        "eigenvector_normalization_type": "unity-diagonal",
        "verification_tolerance": 1e13,
    }

    def __init__(
        self,
        original_csp,
        initial_flow,
        context_flow,
        alignment,
        questions,
        num_dim,
        num_iter,
        cart_sum_args=None,
        cart_estimate_args=None,
        lda_scatter_args=None,
        lda_estimate_args=None,
        eigenvalue_args=None,
        generalized_eigenvalue_args=None,
    ):
        cart_sum_args = {} if cart_sum_args is None else cart_sum_args
        cart_estimate_args = {} if cart_estimate_args is None else cart_estimate_args
        lda_scatter_args = {} if lda_scatter_args is None else lda_scatter_args
        lda_estimate_args = {} if lda_estimate_args is None else lda_estimate_args
        eigenvalue_args = {} if eigenvalue_args is None else eigenvalue_args
        generalized_eigenvalue_args = (
            {} if generalized_eigenvalue_args is None else generalized_eigenvalue_args
        )

        self.cart_sum_jobs = []
        self.cart_estimate_jobs = []
        self.lda_scatter_jobs = []
        self.lda_estimate_jobs = []

        self.last_lda_matrix = None
        self.last_cart_tree = None
        self.last_num_cart_labels = None

        csp = rasr.CommonRasrParameters(base=original_csp)
        csp.acoustic_model_config = original_csp.acoustic_model_config._copy()

        for iteration in range(num_iter):
            csp.acoustic_model_config.state_tying.type = "monophone"
            del csp.acoustic_model_config.state_tying.file

            temp_alignment_flow = mm.cached_alignment_flow(initial_flow, alignment)

            args = {"csp": csp, "alignment_flow": temp_alignment_flow}
            args.update(select_args(cart_sum_args, iteration))
            cart_sum = cart.AccumulateCartStatisticsJob(**args)

            args = {
                "csp": csp,
                "questions": questions,
                "cart_examples": cart_sum.cart_sum,
            }
            args.update(select_args(cart_estimate_args, iteration))
            cart_estimate = cart.EstimateCartJob(**args)

            csp.acoustic_model_config.state_tying.type = "cart"
            csp.acoustic_model_config.state_tying.file = cart_estimate.cart_tree

            temp_alignment_flow = mm.cached_alignment_flow(context_flow, alignment)

            args = {"csp": csp, "alignment_flow": temp_alignment_flow}
            args.update(select_args(lda_scatter_args, iteration))
            lda_scatter = lda.EstimateScatterMatricesJob(**args)

            args = self.default_eigenvalue_params.copy()
            args.update(select_args(eigenvalue_args, iteration))
            eigenvalue_problem_config = lda.build_eigenvalue_problem_config(**args)

            args = self.default_generalized_eigenvalue_params.copy()
            args.update(select_args(generalized_eigenvalue_args, iteration))
            generalized_eigenvalue_problem_config = (
                lda.build_generalized_eigenvalue_problem_config(**args)
            )

            args = {
                "csp": csp,
                "between_class_scatter_matrix": lda_scatter.between_class_scatter_matrix,
                "within_class_scatter_matrix": lda_scatter.within_class_scatter_matrix,
                "reduced_dimension": num_dim,
                "eigenvalue_problem_config": eigenvalue_problem_config,
                "generalized_eigenvalue_problem_config": generalized_eigenvalue_problem_config,
            }
            args.update(select_args(lda_estimate_args, iteration))
            lda_estimate = lda.EstimateLDAMatrixJob(**args)

            initial_flow = features.add_linear_transform(
                context_flow, lda_estimate.lda_matrix
            )

            self.cart_sum_jobs.append(cart_sum)
            self.cart_estimate_jobs.append(cart_estimate)
            self.lda_scatter_jobs.append(lda_scatter)
            self.lda_estimate_jobs.append(lda_estimate)

            self.last_cart_tree = cart_estimate.cart_tree
            self.last_lda_matrix = lda_estimate.lda_matrix
            self.last_num_cart_labels = cart_estimate.num_labels


def select_args(args, iteration):
    result = {}
    result.update(args.get("all", {}))
    result.update(args.get(iteration, {}))
    return result
