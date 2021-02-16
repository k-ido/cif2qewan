#!/usr/bin/env python

import numpy as np
import os


class Hamiltonian(object):
    """
    This class contains the information of Hamiltonian generated by wannier90 code.
    All units are eV and A

    parameters:
      num_wann
      nrpts
      ndegen[1:nrpts]
      ham_r[1:num_wann,1:num_wann,1:nrpts]
      a[1:3,1:3]
      b[1:3,1:3]
    """

    def __init__(self, file_hr="", reorder=False):
        """ read file_hr and set following variables
            num_wann:
            nrpts:
            ndegen:
            ham_r:
            optionally, read file_nnkp and set a, b
        """
        self.reorder = reorder
        if file_hr:
            self._read_hr(file_hr)

    def _read_hr(self, file_hr):
        try:
            if os.path.exists(file_hr):
                fp = open(file_hr, 'r')
            else:
                raise Exception
            fp.readline()   # empty line
            self.num_wann = int( fp.readline() )
            self.nrpts = int( fp.readline() )

            # print(self.num_wann, self.nrpts)

            ndegen = []
            for i in range( int(self.nrpts/15)+1 ):
                ndegen += map(int, fp.readline().split())
                if len(ndegen) >= self.nrpts: break
            self.ndegen = np.array(ndegen)

            # print(ndegen)

            self.ham_r = np.zeros((self.num_wann, self.num_wann, self.nrpts), dtype=np.complex)
            self.irvec = np.zeros((3,self.nrpts), dtype=np.float64)

            self.ir0 = -1
            for i in range(self.nrpts):
                for m in range(self.num_wann):
                    for n in range (self.num_wann):
                        (irx, iry, irz, p, q, tr, ti) = fp.readline().split()
                        if m == 0 and n == 0:
                            # self.irvec[0:3,i] = np.array(map(int,[irx,iry,irz]))
                            self.irvec[0:3, i] = np.array([int(x) for x in [irx, iry, irz]])
                            if np.all(self.irvec[0:3, i] == 0):
                                self.ir0 = i
                        # self.ham_r[m,n,i] = float(tr) + float(ti)*1j
                        self.ham_r[n, m, i] = float(tr) + float(ti)*1j
            fp.close()
        except Exception as e:
            print ("failed to read: " + file_hr)
            print ('type:' + str(type(e)))
            print ('args:' + str(e.args))
            print (str(e))

    def diagonalize(self, k):
        """ diagonalize H(k) and return ek, v
        """
        kr = np.dot(k, self.irvec)
        pi = np.pi
        factor = np.exp(2*pi*1j*kr)/self.ndegen
        ham = np.dot(self.ham_r, factor)
        # return np.linalg.eigh(ham)
        (e, v) = np.linalg.eigh(ham)
        # e_n v_n[i] = ham[i,j] v_n[j]:   e[n], v[j,n]
        # ham = np.dot(self.ham_r, factor)
        # correct
        # p = np.dot(ham, v) - np.einsum("i,ji->ji", e, v)
        # not correct
        # p = np.dot(ham, np.transpose(v)) - np.einsum("i,ji->ji", e, np.transpose(v))
        # for a in p:
        #    if ( sum(a * np.conjugate(a)) > 1e-9 ) : print (a)
        # return (e,v)
        return (e, v)


class Nscfout:
    """
    Nscf-Calculation must be done with "verbosity = 'high'" !
    """
    def __init__(self, nscf_out):
        with open(nscf_out, "r") as fp:
            lines = fp.readlines()
            for i, line in enumerate(lines):
                if "Fermi energy" in line:
                    self.ef = float(line[26:35])
                if "number of Kohn-Sham" in line:
                    self.nbnd = int(line[35:])
                if "number of k points=" in line:
                    self.nk = int(line[25:31])
                    self.kp_cart = np.zeros([self.nk, 3])
                    self.kp_cryst = np.zeros([self.nk, 3])
                    self.wk = np.zeros([self.nk])
                    for j in range(self.nk):
                        self.kp_cart[j] = np.array( [float(x) for x in lines[i+j+2][20:56].split()] )
                        self.wk[j] = float(lines[i+j+2][65:])
                        self.kp_cryst[j] = np.array( [float(x) for x in lines[i+j+4+self.nk][20:56].split()] )
            self.energy = np.zeros([self.nk, self.nbnd])
            nline, nlinemod = divmod(self.nbnd, 8)
            if(nlinemod > 0): nline += 1
            for j in range(self.nk):
                kp_str = "k =%7.4f%7.4f%7.4f" % tuple(self.kp_cart[j])
                for i, line in enumerate(lines):
                    if kp_str in line:
                        self.energy[j, :] = [float(x) for x in ''.join(lines[i+2:i+2+nline]).split()]


def get_nexclude(pwscf_win):
    nexclude = 0
    with open(pwscf_win) as fp:
        for line in fp.readlines():
            if "exclude" in line:
                nexclude = int(line.split("-")[1])
    return nexclude


if __name__ == "__main__":
    nscf_data = Nscfout("check_wannier/nscf.out")
    nexclude = get_nexclude("./pwscf.win")
    h = Hamiltonian(file_hr="./pwscf_hr.dat")

    # Energy window for check
    emin = -100.0
    emax = 0.0

    # calculate energy difference
    delta_sum = 0
    delta_max = 0
    nek = 0
    for i in range(nscf_data.nk):
        (ek, v) = h.diagonalize(nscf_data.kp_cryst[i])

        nek_low = np.sum(ek - nscf_data.ef < emin)
        nek_max = np.sum(ek - nscf_data.ef < emax)
        if nexclude + nek_max > nscf_data.nbnd:
            nek_max = nscf_data.nbnd - nexclude
        if nek_max == nek_low:
            continue

        nek += nek_max - nek_low
        ediff = (ek[nek_low:nek_max] - nscf_data.energy[i, nexclude+nek_low:nexclude+nek_max])**2
        delta_sum += np.sum(ediff)
        delta_max = max([delta_max, np.max(ediff)])

    # output the results
    with open("check_wannier/CONV", "w") as fp:
        fp.write("# energy window [{:>5.2f}:{:>5.2f}]\n".format(emin, emax))
        if nek > 0:
            fp.write("average diff = {:>15.8f}\n".format(np.sqrt(delta_sum/nek)))
        else:
            fp.write("average diff = NaN")
        fp.write("max diff     = {:>15.8f}\n".format(np.sqrt(delta_max)))


