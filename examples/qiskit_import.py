import qiskit
from qsearch.qiskit import qiskit_to_qsearch
from qsearch import multistart_solvers, utils, Options, defaults, unitaries
from qsearch.assembler import assemble, ASSEMBLY_IBMOPENQASM
from qsrs import native_from_object
import matplotlib.pyplot as plt

import os.path

if __name__ == '__main__':
    # use the multistart solver for more accurate results, this uses 24 starting points
    solv = multistart_solvers.MultiStart_Solver(24)


    backend = qiskit.BasicAer.get_backend('unitary_simulator')
    # load a qft5 solution
    qc1 = qiskit.QuantumCircuit.from_qasm_file(f'{os.path.dirname(__file__)}/qft5.qasm')
    # generate a unitary from the Qiskit circuit
    job = qiskit.execute(qc1, backend)
    U2 = job.result().get_unitary()
    U2 = utils.endian_reverse(U2) # switch from Qiskit endianess qsearch endianess
    # tell the optimizer what we are solving for
    opts = Options()
    opts.target = unitaries.qft(32)
    opts.set_defaults(**defaults.standard_defaults)
    opts.set_smart_defaults(**defaults.standard_smart_defaults)

    #qc1.draw(output='mpl')
    #plt.show()
    circ = qiskit_to_qsearch(qc1)
    print(circ.validate_structure())
    U1, vec = solv.solve_for_unitary(circ, opts)
    qc2 = qiskit.QuantumCircuit.from_qasm_str(assemble(qiskit_to_qsearch(qc1), vec, ASSEMBLY_IBMOPENQASM))
    #qc2.draw(output='mpl')
    #plt.show()
    print(utils.matrix_distance_squared(U1, unitaries.qft(32)))