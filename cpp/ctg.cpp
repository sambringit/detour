// Native backward Dijkstra over directed-edge states for detour (cost_to_go).
//
// Mirrors RoadNetwork.cost_to_go in detour/world.py step for step so that results
// are identical to the Python code, including which equal-cost path settles first:
//   * states are directed edges, indexed by edge id (state (u, v) == edge u->v)
//   * predecessors of state (m, w) are visited in inn[m] order (CSR below keeps it)
//   * heap order is (cost, counter); the counter starts at 0 for the target's in-edges
//     and is pre-incremented for every later push, exactly like the Python `k`
//   * an entry is only replaced on a strict `<`
//   * cost is computed as (cost + step) + penalty, in double precision
// Build WITHOUT -ffast-math and with -ffp-contract=off so no FMA changes the rounding.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <cstdint>
#include <limits>
#include <queue>
#include <stdexcept>
#include <vector>

namespace py = pybind11;

namespace {

struct Entry {
    double cost;
    std::int64_t counter;
    std::int32_t edge;
};

struct Later {  // min-heap on (cost, counter); counters are unique
    bool operator()(const Entry& a, const Entry& b) const {
        if (a.cost != b.cost) return a.cost > b.cost;
        return a.counter > b.counter;
    }
};

void cost_to_go_core(const std::int32_t* edge_from, const std::int32_t* edge_to,
                     const double* edge_time, const std::int64_t* in_off,
                     const std::int32_t* in_edges, const std::uint8_t* uturn_ok,
                     std::int32_t target, double penalty, double* cost,
                     std::uint8_t* flag) {
    std::priority_queue<Entry, std::vector<Entry>, Later> heap;
    std::int64_t k = 0;
    for (std::int64_t i = in_off[target]; i < in_off[target + 1]; ++i) {
        const std::int32_t e = in_edges[i];
        cost[e] = 0.0;
        flag[e] = 0;
        heap.push(Entry{0.0, k, e});
        ++k;
    }
    while (!heap.empty()) {
        const Entry top = heap.top();
        heap.pop();
        if (top.cost > cost[top.edge]) continue;  // stale entry
        const std::uint8_t cur_flag = flag[top.edge];
        const std::int32_t m = edge_from[top.edge];
        const std::int32_t w = edge_to[top.edge];
        const double step = edge_time[top.edge];
        for (std::int64_t i = in_off[m]; i < in_off[m + 1]; ++i) {
            const std::int32_t f = in_edges[i];  // predecessor state (u, m)
            const bool rev = (edge_from[f] == w);
            if (rev && !uturn_ok[m]) continue;
            double c = top.cost + step;
            if (rev) c += penalty;
            if (c < cost[f]) {  // strict <; cost starts at +inf for "not in g"
                cost[f] = c;
                flag[f] = (cur_flag || rev) ? 1 : 0;
                ++k;
                heap.push(Entry{c, k, f});
            }
        }
    }
}

template <typename T>
using Arr = py::array_t<T, py::array::c_style | py::array::forcecast>;

std::pair<py::array_t<double>, py::array_t<std::uint8_t>> cost_to_go(
    Arr<std::int32_t> edge_from, Arr<std::int32_t> edge_to, Arr<double> edge_time,
    Arr<std::int64_t> in_off, Arr<std::int32_t> in_edges, Arr<std::uint8_t> uturn_ok,
    std::int32_t target, double penalty) {
    const py::ssize_t n_edges = edge_from.size();
    const py::ssize_t n_nodes = uturn_ok.size();
    if (edge_to.size() != n_edges || edge_time.size() != n_edges || in_edges.size() != n_edges)
        throw std::invalid_argument("edge arrays must all have the same length");
    if (in_off.size() != n_nodes + 1) throw std::invalid_argument("in_off must have n_nodes + 1 entries");
    if (target < 0 || target >= n_nodes) throw std::out_of_range("target node index out of range");

    py::array_t<double> cost(n_edges);
    py::array_t<std::uint8_t> flag(n_edges);
    double* cp = cost.mutable_data();
    std::uint8_t* fp = flag.mutable_data();
    std::fill(cp, cp + n_edges, std::numeric_limits<double>::infinity());
    std::fill(fp, fp + n_edges, std::uint8_t{0});
    {
        py::gil_scoped_release release;
        cost_to_go_core(edge_from.data(), edge_to.data(), edge_time.data(), in_off.data(),
                        in_edges.data(), uturn_ok.data(), target, penalty, cp, fp);
    }
    return {cost, flag};
}

}  // namespace

PYBIND11_MODULE(_ctg, m) {
    m.doc() = "Native cost_to_go for detour (optional; pure-Python fallback lives in world.py)";
    m.def("cost_to_go", &cost_to_go, py::arg("edge_from"), py::arg("edge_to"),
          py::arg("edge_time"), py::arg("in_off"), py::arg("in_edges"), py::arg("uturn_ok"),
          py::arg("target"), py::arg("penalty"),
          "Returns (seconds[float64, inf = unreachable], has_uturn[uint8]) per directed edge id.");
}
