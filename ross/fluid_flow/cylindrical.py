import time

import numpy as np
from numpy.linalg import pinv
from scipy.optimize import curve_fit, minimize

from ross.units import Q_, check_units


class THDCylindrical:
    """This class calculates the pressure and temperature field in oil film of a cylindrical bearing, with two (2) pads. It is also possible to obtain the stiffness and damping coefficients.

    Parameters
    ----------
    Bearing Geometry
    ^^^^^^^^^^^^^^^^
    Describes the geometric characteristics.
    L : float, pint.Quantity
        Bearing length. Default unit is meter.
    R : float
        Rotor radius. The unit is meter.
    c_r : float
        Radial clearence between rotor and bearing. The unit is meter.
    betha_s : float
        Arc length of each pad. The unit is degree.


    Operation conditions
    ^^^^^^^^^^^^^^^^^^^^
    Describes the operation conditions of the bearing.
    speed : float, pint.Quantity
        Rotor rotational speed. Default unit is rad/s.
    Wx : Float
        Load in X direction. The unit is newton.
    Wy : Float
        Load in Y direction. The unit is newton.

    Fluid propierties
    ^^^^^^^^^^^^^^^^^
    Describes the fluid characteristics.
    mu_ref : float
        Fluid reference viscosity. The unit is Pa*s.
    rho : float, pint.Quantity
        Fluid density. Default unit is kg/m^3.
    k_t :  Float
        Fluid thermal conductivity. The unit is J/(s*m*°C).
    Cp : float
        Fluid specific heat. The unit is J/(kg*°C).
    Treserv : float
        Oil reservoir temperature. The unit is celsius.
    fat_mixt : list, numpy array, tuple or float
        Ratio of oil in Treserv temperature that mixes with the circulating oil.
        Is required one fat_mixt per pad.

    Viscosity interpolation
    ^^^^^^^^^^^^^^^^^^^^^^^
    Interpolation data required.
    T_muI : float
        Inferior limit temperature. The unit is celsius.
    T_muF : float
        Upper limit temperature. The unit is celsius.
    mu_I : float
        Inferior limit viscosity. The unit is Pa*s.
    mu_F : float
        Upper limit viscosity. The unit is Pa*s.

    Turbulence Model
    ^^^^^^^^^^^^^^^^
    Turbulence model to improve analysis in higher speed.The model represents
    the turbulence by eddy diffusivities.
    Reyn : Array
        The Reynolds number is a dimensionless number used to calculate the
        fluid flow regime inside the bearing.
    delta_turb : float
        Eddy viscosity scaling factor. Coefficient to assign weight to laminar,
        transitional and turbulent flows to calculate viscosity.

    Mesh discretization
    ^^^^^^^^^^^^^^^^^^^
    Describes the discretization of the bearing.
    ntheta : int
        Number of volumes along the direction theta (direction of flow).
    nz : int
        Number of volumes along the Z direction (axial direction).



    Returns
    -------
    A THDCylindrical object.

    References
    ----------
    .. [1] BARBOSA, J. S.; LOBATO, FRAN S.; CAMPANINE SICCHIERI, LEONARDO;CAVALINI JR, ALDEMIR AP. ; STEFFEN JR, VALDER. Determinação da Posição de Equilíbrio em Mancais Hidrodinâmicos Cilíndricos usando o Algoritmo de Evolução Diferencial. REVISTA CEREUS, v. 10, p. 224-239, 2018. ..
    .. [2] DANIEL, G.B. Desenvolvimento de um Modelo Termohidrodinâmico para Análise em Mancais Segmentados. Campinas: Faculdade de Engenharia Mecânica, Universidade Estadual de Campinas, 2012. Tese (Doutorado). ..
    .. [3] NICOLETTI, R., Efeitos Térmicos em Mancais Segmentados Híbridos – Teoria e Experimento. 1999. Dissertação de Mestrado. Universidade Estadual de Campinas, Campinas. ..
    .. [4] SUGANAMI, T.; SZERI, A. Z. A thermohydrodynamic analysis of journal bearings. 1979. ..
    .. [5] LUND, J. W.; THOMSEN, K. K. A calculation method and data for the dynamic coefficients of oil-lubricated journal bearings. Topics in fluid film bearing and rotor bearing system design and optimization, n. 1000118, 1978. ..

    Attributes
    ----------
    Pdim : array
        Dimensional pressure field. The unit is pascal.
    dPdz : array
        Differential pressure field in z direction.
    dPdy : array
        Differential pressure field in theta direction.
    Tdim : array
        Dimensional temperature field. The unit is celsius.
    Fhx : float
        Force in X direction. The unit is newton.
    Fhy : float
        Force in Y direction. The unit is newton.
    equilibrium_pos : array
        Array with excentricity ratio and attitude angle information.
        Its shape is: array([excentricity, angle])

    Examples
    --------
    >>> from ross.fluid_flow.cylindrical import cylindrical_bearing_example
    >>> x0 = [0.1,-0.1]
    >>> bearing = cylindrical_bearing_example()
    >>> bearing.run(x0)
    >>> bearing.equilibrium_pos
    array([ 0.57085649, -0.70347548])
    """

    @check_units
    def __init__(
        self,
        L,
        R,
        c_r,
        n_theta,
        n_z,
        n_y,
        betha_s,
        mu_ref,
        speed,
        Wx,
        Wy,
        k_t,
        Cp,
        rho,
        T_reserv,
        fat_mixt,
        T_muI,
        T_muF,
        mu_I,
        mu_F,
        sommerfeld_type=2,
    ):

        self.L = L
        self.R = R
        self.c_r = c_r
        self.n_theta = n_theta
        self.n_z = n_z
        self.n_y = n_y
        self.mu_ref = mu_ref
        self.speed = speed
        self.Wx = Wx
        self.Wy = Wy
        self.k_t = k_t
        self.Cp = Cp
        self.rho = rho
        self.T_reserv = T_reserv
        self.fat_mixt = np.array(fat_mixt)
        self.equilibrium_pos = None
        self.sommerfeld_type = sommerfeld_type

        if self.n_y == None:
            self.n_y = self.n_theta

        self.betha_s_dg = betha_s
        self.betha_s = betha_s * np.pi / 180

        self.n_pad = 2

        self.thetaI = 0
        self.thetaF = self.betha_s
        self.dtheta = (self.thetaF - self.thetaI) / (self.n_theta)

        ##
        # Dimensionless discretization variables

        self.dY = 1 / self.n_y
        self.dZ = 1 / self.n_z

        # Z-axis direction

        self.Z_I = 0
        self.Z_F = 1
        Z = np.zeros((self.n_z + 2))

        Z[0] = self.Z_I
        Z[self.n_z + 1] = self.Z_F
        Z[1 : self.n_z + 1] = np.arange(self.Z_I + 0.5 * self.dZ, self.Z_F, self.dZ)
        self.Z = Z

        # Dimensionalization

        self.dz = self.dZ * self.L
        self.dy = self.dY * self.betha_s * self.R

        self.Zdim = self.Z * L

        # Interpolation coefficients
        self.a, self.b = self._interpol(T_muI, T_muF, mu_I, mu_F)

    def _forces(self, x0, y0, xpt0, ypt0):
        """Calculates the forces in Y and X direction.

        Parameters
        ----------
        x0 : array, float
            If the other parameters are None, x0 is an array with eccentricity ratio and attitude angle.
            Else, x0 is the position of the center of the rotor in the x-axis.
        y0 : float
            The position of the center of the rotor in the y-axis.
        xpt0 : float
            The speed of the center of the rotor in the x-axis.
        ypt0 : float
            The speed of the center of the rotor in the y-axis.


        Returns
        -------
        Fhx : float
            Force in X direction. The unit is newton.
        Fhy : float
            Force in Y direction. The unit is newton.
        """
        if y0 is None and xpt0 is None and ypt0 is None:
            self.x0 = x0

            xr = self.x0[0] * self.c_r * np.cos(self.x0[1])
            yr = self.x0[0] * self.c_r * np.sin(self.x0[1])
            self.Y = yr / self.c_r
            self.X = xr / self.c_r

            self.Xpt = 0
            self.Ypt = 0
        else:
            self.X = x0 / self.c_r
            self.Y = y0 / self.c_r

            self.Xpt = xpt0 / (self.c_r * self.speed)
            self.Ypt = ypt0 / (self.c_r * self.speed)

        T_conv = 0.8 * self.T_reserv

        T_mist = self.T_reserv * np.ones(self.n_pad)

        Reyn = np.zeros((self.n_z, self.n_theta, self.n_pad))

        pad_ct = [ang for ang in range(0, 360, int(360 / self.n_pad))]

        self.thetaI = np.radians(
            [pad + (180 / self.n_pad) - (self.betha_s_dg / 2) for pad in pad_ct]
        )

        self.thetaF = np.radians(
            [pad + (180 / self.n_pad) + (self.betha_s_dg / 2) for pad in pad_ct]
        )

        Ytheta = [
            np.linspace(t1, t2, self.n_theta)
            for t1, t2 in zip(self.thetaI, self.thetaF)
        ]

        self.pad_ct = [ang for ang in range(0, 360, int(360 / self.n_pad))]

        self.thetaI = np.radians(
            [pad + (180 / self.n_pad) - (self.betha_s_dg / 2) for pad in self.pad_ct]
        )

        self.thetaF = np.radians(
            [pad + (180 / self.n_pad) + (self.betha_s_dg / 2) for pad in self.pad_ct]
        )

        Ytheta = [
            np.linspace(t1, t2, self.n_theta)
            for t1, t2 in zip(self.thetaI, self.thetaF)
        ]

        while (T_mist[0] - T_conv) >= 1e-2:

            self.P = np.zeros((self.n_z, self.n_theta, self.n_pad))
            dPdy = np.zeros((self.n_z, self.n_theta, self.n_pad))
            dPdz = np.zeros((self.n_z, self.n_theta, self.n_pad))
            T = np.ones((self.n_z, self.n_theta, self.n_pad))
            T_new = np.ones((self.n_z, self.n_theta, self.n_pad)) * 1.2

            T_conv = T_mist[0]

            mu_new = 1.1 * np.ones((self.n_z, self.n_theta, self.n_pad))
            mu_turb = 1.3 * np.ones((self.n_z, self.n_theta, self.n_pad))

            PP = np.zeros(((self.n_z), (2 * self.n_theta)))

            nk = (self.n_z) * (self.n_theta)

            Mat_coef = np.zeros((nk, nk))
            Mat_coef_T = np.zeros((nk, nk))
            b = np.zeros((nk, 1))
            b_T = np.zeros((nk, 1))

            for n_p in np.arange(self.n_pad):

                T_ref = T_mist[n_p - 1]

                # Temperature convergence while

                while (
                    np.linalg.norm(T_new[:, :, n_p] - T[:, :, n_p])
                    / np.linalg.norm(T[:, :, n_p])
                    >= 1e-3
                ):

                    T_ref = T_mist[n_p - 1]

                    mu = mu_new
                    self.mu_l=mu_new
                    
                    T[:, :, n_p] = T_new[:, :, n_p]

                    ki = 0
                    kj = 0
                    k = 0

                    # Solution of pressure field initialization

                    for ii in np.arange((self.Z_I + 0.5 * self.dZ), self.Z_F, self.dZ):
                        for jj in np.arange(
                            self.thetaI[n_p] + (self.dtheta / 2),
                            self.thetaF[n_p],
                            self.dtheta,
                        ):

                            hP = 1 - self.X * np.cos(jj) - self.Y * np.sin(jj)
                            he = (
                                1
                                - self.X * np.cos(jj + 0.5 * self.dtheta)
                                - self.Y * np.sin(jj + 0.5 * self.dtheta)
                            )
                            hw = (
                                1
                                - self.X * np.cos(jj - 0.5 * self.dtheta)
                                - self.Y * np.sin(jj - 0.5 * self.dtheta)
                            )
                            hn = hP
                            hs = hn

                            if kj == 0 and ki == 0:
                                MU_e = 0.5 * (mu[ki, kj] + mu[ki, kj + 1])
                                MU_w = mu[ki, kj]
                                MU_s = mu[ki, kj]
                                MU_n = 0.5 * (mu[ki, kj] + mu[ki + 1, kj])

                            if kj == 0 and ki > 0 and ki < self.n_z - 1:
                                MU_e = 0.5 * (mu[ki, kj] + mu[ki, kj + 1])
                                MU_w = mu[ki, kj]
                                MU_s = 0.5 * (mu[ki, kj] + mu[ki - 1, kj])
                                MU_n = 0.5 * (mu[ki, kj] + mu[ki + 1, kj])

                            if kj == 0 and ki == self.n_z - 1:
                                MU_e = 0.5 * (mu[ki, kj] + mu[ki, kj + 1])
                                MU_w = mu[ki, kj]
                                MU_s = 0.5 * (mu[ki, kj] + mu[ki - 1, kj])
                                MU_n = mu[ki, kj]

                            if ki == 0 and kj > 0 and kj < self.n_theta - 1:
                                MU_e = 0.5 * (mu[ki, kj] + mu[ki, kj + 1])
                                MU_w = 0.5 * (mu[ki, kj] + mu[ki, kj - 1])
                                MU_s = mu[ki, kj]
                                MU_n = 0.5 * (mu[ki, kj] + mu[ki + 1, kj])

                            if (
                                kj > 0
                                and kj < self.n_theta - 1
                                and ki > 0
                                and ki < self.n_z - 1
                            ):
                                MU_e = 0.5 * (mu[ki, kj] + mu[ki, kj + 1])
                                MU_w = 0.5 * (mu[ki, kj] + mu[ki, kj - 1])
                                MU_s = 0.5 * (mu[ki, kj] + mu[ki - 1, kj])
                                MU_n = 0.5 * (mu[ki, kj] + mu[ki + 1, kj])

                            if ki == self.n_z - 1 and kj > 0 and kj < self.n_theta - 1:
                                MU_e = 0.5 * (mu[ki, kj] + mu[ki, kj + 1])
                                MU_w = 0.5 * (mu[ki, kj] + mu[ki, kj - 1])
                                MU_s = 0.5 * (mu[ki, kj] + mu[ki - 1, kj])
                                MU_n = mu[ki, kj]

                            if ki == 0 and kj == self.n_theta - 1:
                                MU_e = mu[ki, kj]
                                MU_w = 0.5 * (mu[ki, kj] + mu[ki, kj - 1])
                                MU_s = mu[ki, kj]
                                MU_n = 0.5 * (mu[ki, kj] + mu[ki + 1, kj])

                            if kj == self.n_theta - 1 and ki > 0 and ki < self.n_z - 1:
                                MU_e = mu[ki, kj]
                                MU_w = 0.5 * (mu[ki, kj] + mu[ki, kj - 1])
                                MU_s = 0.5 * (mu[ki, kj] + mu[ki - 1, kj])
                                MU_n = 0.5 * (mu[ki, kj] + mu[ki + 1, kj])

                            if kj == self.n_theta - 1 and ki == self.n_z - 1:
                                MU_e = mu[ki, kj]
                                MU_w = 0.5 * (mu[ki, kj] + mu[ki, kj - 1])
                                MU_s = 0.5 * (mu[ki, kj] + mu[ki - 1, kj])
                                MU_n = mu[ki, kj]

                            CE = (self.dZ * he**3) / (
                                12 * MU_e[n_p] * self.dY * self.betha_s**2
                            )
                            CW = (self.dZ * hw**3) / (
                                12 * MU_w[n_p] * self.dY * self.betha_s**2
                            )
                            CN = (self.dY * (self.R**2) * hn**3) / (
                                12 * MU_n[n_p] * self.dZ * self.L**2
                            )
                            CS = (self.dY * (self.R**2) * hs**3) / (
                                12 * MU_s[n_p] * self.dZ * self.L**2
                            )
                            CP = -(CE + CW + CN + CS)

                            B = (self.dZ / (2 * self.betha_s)) * (he - hw) - (
                                (self.Ypt * np.cos(jj) + self.Xpt * np.sin(jj))
                                * self.dy
                                * self.dZ
                            )

                            k = k + 1
                            b[k - 1, 0] = B

                            if ki == 0 and kj == 0:
                                Mat_coef[k - 1, k - 1] = CP - CS - CW
                                Mat_coef[k - 1, k] = CE
                                Mat_coef[k - 1, k + self.n_theta - 1] = CN

                            elif kj == 0 and ki > 0 and ki < self.n_z - 1:
                                Mat_coef[k - 1, k - 1] = CP - CW
                                Mat_coef[k - 1, k] = CE
                                Mat_coef[k - 1, k - self.n_theta - 1] = CS
                                Mat_coef[k - 1, k + self.n_theta - 1] = CN

                            elif kj == 0 and ki == self.n_z - 1:
                                Mat_coef[k - 1, k - 1] = CP - CN - CW
                                Mat_coef[k - 1, k] = CE
                                Mat_coef[k - 1, k - self.n_theta - 1] = CS

                            elif ki == 0 and kj > 0 and kj < self.n_y - 1:
                                Mat_coef[k - 1, k - 1] = CP - CS
                                Mat_coef[k - 1, k] = CE
                                Mat_coef[k - 1, k - 2] = CW
                                Mat_coef[k - 1, k + self.n_theta - 1] = CN

                            elif (
                                ki > 0
                                and ki < self.n_z - 1
                                and kj > 0
                                and kj < self.n_y - 1
                            ):
                                Mat_coef[k - 1, k - 1] = CP
                                Mat_coef[k - 1, k - 2] = CW
                                Mat_coef[k - 1, k - self.n_theta - 1] = CS
                                Mat_coef[k - 1, k + self.n_theta - 1] = CN
                                Mat_coef[k - 1, k] = CE

                            elif ki == self.n_z - 1 and kj > 0 and kj < self.n_y - 1:
                                Mat_coef[k - 1, k - 1] = CP - CN
                                Mat_coef[k - 1, k] = CE
                                Mat_coef[k - 1, k - 2] = CW
                                Mat_coef[k - 1, k - self.n_theta - 1] = CS

                            elif ki == 0 and kj == self.n_y - 1:
                                Mat_coef[k - 1, k - 1] = CP - CE - CS
                                Mat_coef[k - 1, k - 2] = CW
                                Mat_coef[k - 1, k + self.n_theta - 1] = CN

                            elif kj == self.n_y - 1 and ki > 0 and ki < self.n_z - 1:
                                Mat_coef[k - 1, k - 1] = CP - CE
                                Mat_coef[k - 1, k - 2] = CW
                                Mat_coef[k - 1, k - self.n_theta - 1] = CS
                                Mat_coef[k - 1, k + self.n_theta - 1] = CN

                            elif ki == self.n_z - 1 and kj == self.n_y - 1:
                                Mat_coef[k - 1, k - 1] = CP - CE - CN
                                Mat_coef[k - 1, k - 2] = CW
                                Mat_coef[k - 1, k - self.n_theta - 1] = CS

                            kj = kj + 1

                        kj = 0
                        ki = ki + 1

                    # Solution of pressure field end

                    p = np.linalg.solve(Mat_coef, b)
                    cont = 0

                    for i in np.arange(self.n_z):
                        for j in np.arange(self.n_theta):

                            self.P[i, j, n_p] = p[cont]
                            cont = cont + 1

                            if self.P[i, j, n_p] < 0:
                                self.P[i, j, n_p] = 0

                    # Dimensional pressure fied

                    self.Pdim = (self.P * self.mu_ref * self.speed * (self.R**2)) / (
                        self.c_r**2
                    )

                    ki = 0
                    kj = 0
                    k = 0

                    # Solution of temperature field initialization

                    for ii in np.arange(
                        (self.Z_I + 0.5 * self.dZ), (self.Z_F), self.dZ
                    ):
                        for jj in np.arange(
                            self.thetaI[n_p] + (self.dtheta / 2),
                            self.thetaF[n_p],
                            self.dtheta,
                        ):

                            # Pressure gradients

                            if kj == 0 and ki == 0:
                                dPdy[ki, kj, n_p] = (self.P[ki, kj + 1, n_p] - 0) / (
                                    2 * self.dY
                                )
                                dPdz[ki, kj, n_p] = (self.P[ki + 1, kj, n_p] - 0) / (
                                    2 * self.dZ
                                )

                            if kj == 0 and ki > 0 and ki < self.n_z - 1:
                                dPdy[ki, kj, n_p] = (self.P[ki, kj + 1, n_p] - 0) / (
                                    2 * self.dY
                                )
                                dPdz[ki, kj, n_p] = (
                                    self.P[ki + 1, kj, n_p] - self.P[ki - 1, kj, n_p]
                                ) / (2 * self.dZ)

                            if kj == 0 and ki == self.n_z - 1:
                                dPdy[ki, kj, n_p] = (self.P[ki, kj + 1, n_p] - 0) / (
                                    2 * self.dY
                                )
                                dPdz[ki, kj, n_p] = (0 - self.P[ki - 1, kj, n_p]) / (
                                    2 * self.dZ
                                )

                            if ki == 0 and kj > 0 and kj < self.n_theta - 1:
                                dPdy[ki, kj, n_p] = (
                                    self.P[ki, kj + 1, n_p] - self.P[ki, kj - 1, n_p]
                                ) / (2 * self.dY)
                                dPdz[ki, kj, n_p] = (self.P[ki + 1, kj, n_p] - 0) / (
                                    2 * self.dZ
                                )

                            if (
                                kj > 0
                                and kj < self.n_theta - 1
                                and ki > 0
                                and ki < self.n_z - 1
                            ):
                                dPdy[ki, kj, n_p] = (
                                    self.P[ki, kj + 1, n_p] - self.P[ki, kj - 1, n_p]
                                ) / (2 * self.dY)
                                dPdz[ki, kj, n_p] = (
                                    self.P[ki + 1, kj, n_p] - self.P[ki - 1, kj, n_p]
                                ) / (2 * self.dZ)

                            if ki == self.n_z - 1 and kj > 0 and kj < self.n_theta - 1:
                                dPdy[ki, kj, n_p] = (
                                    self.P[ki, kj + 1, n_p] - self.P[ki, kj - 1, n_p]
                                ) / (2 * self.dY)
                                dPdz[ki, kj, n_p] = (0 - self.P[ki - 1, kj, n_p]) / (
                                    2 * self.dZ
                                )

                            if ki == 0 and kj == self.n_theta - 1:
                                dPdy[ki, kj, n_p] = (0 - self.P[ki, kj - 1, n_p]) / (
                                    2 * self.dY
                                )
                                dPdz[ki, kj, n_p] = (self.P[ki + 1, kj, n_p] - 0) / (
                                    2 * self.dZ
                                )

                            if kj == self.n_theta - 1 and ki > 0 and ki < self.n_z - 1:
                                dPdy[ki, kj, n_p] = (0 - self.P[ki, kj - 1, n_p]) / (
                                    2 * self.dY
                                )
                                dPdz[ki, kj, n_p] = (
                                    self.P[ki + 1, kj, n_p] - self.P[ki - 1, kj, n_p]
                                ) / (2 * self.dZ)

                            if kj == self.n_theta - 1 and ki == self.n_z - 1:
                                dPdy[ki, kj, n_p] = (0 - self.P[ki, kj - 1, n_p]) / (
                                    2 * self.dY
                                )
                                dPdz[ki, kj, n_p] = (0 - self.P[ki - 1, kj, n_p]) / (
                                    2 * self.dZ
                                )

                            HP = 1 - self.X * np.cos(jj) - self.Y * np.sin(jj)
                            hpt = -self.Ypt * np.cos(jj) + self.Xpt * np.sin(jj)

                            mu_p = mu[ki, kj, n_p]

                            Reyn[ki, kj, n_p] = (
                                self.rho
                                * self.speed
                                * self.R
                                * (HP / self.L)
                                * self.c_r
                                / (self.mu_ref)
                            )

                            if Reyn[ki, kj, n_p] <= 500:

                                self.delta_turb = 0

                            elif Reyn[ki, kj, n_p] > 400 and Reyn[ki, kj, n_p] <= 1000:

                                self.delta_turb = 1 - (
                                    (1000 - Reyn[ki, kj, n_p]) / 500
                                ) ** (1 / 8)

                            elif Reyn[ki, kj, n_p] > 1000:

                                self.delta_turb = 1

                            dudy = ((HP / mu_turb[ki, kj, n_p]) * dPdy[ki, kj, n_p]) - (
                                self.speed / HP
                            )

                            dwdy = (HP / mu_turb[ki, kj, n_p]) * dPdz[ki, kj, n_p]

                            tal = mu_turb[ki, kj, n_p] * np.sqrt(
                                (dudy**2) + (dwdy**2)
                            )

                            x_wall = (
                                (HP * self.c_r * 2)
                                / (self.mu_ref * mu_turb[ki, kj, n_p] / self.rho)
                            ) * ((abs(tal) / self.rho) ** 0.5)

                            emv = 0.4 * (x_wall - (10.7 * np.tanh(x_wall / 10.7)))

                            mu_turb[ki, kj, n_p] = mu_p * (1 + (self.delta_turb * emv))

                            mi_t = mu_turb[ki, kj, n_p]

                            AE = -(self.k_t * HP * self.dZ) / (
                                self.rho
                                * self.Cp
                                * self.speed
                                * ((self.betha_s * self.R) ** 2)
                                * self.dY
                            )
                            AW = (
                                (
                                    ((HP**3) * dPdy[ki, kj, n_p] * self.dZ)
                                    / (12 * mi_t * (self.betha_s**2))
                                )
                                - ((HP) * self.dZ / (2 * self.betha_s))
                                - (
                                    (self.k_t * HP * self.dZ)
                                    / (
                                        self.rho
                                        * self.Cp
                                        * self.speed
                                        * ((self.betha_s * self.R) ** 2)
                                        * self.dY
                                    )
                                )
                            )
                            AN = -(self.k_t * HP * self.dY) / (
                                self.rho
                                * self.Cp
                                * self.speed
                                * (self.L**2)
                                * self.dZ
                            )
                            AS = (
                                (
                                    (self.R**2)
                                    * (HP**3)
                                    * dPdz[ki, kj, n_p]
                                    * self.dY
                                )
                                / (12 * (self.L**2) * mi_t)
                            ) - (
                                (self.k_t * HP * self.dY)
                                / (
                                    self.rho
                                    * self.Cp
                                    * self.speed
                                    * (self.L**2)
                                    * self.dZ
                                )
                            )
                            AP = -(AE + AW + AN + AS)

                            auxb_T = (self.speed * self.mu_ref) / (
                                self.rho * self.Cp * self.T_reserv * self.c_r
                            )
                            b_TG = (
                                self.mu_ref
                                * self.speed
                                * (self.R**2)
                                * self.dY
                                * self.dZ
                                * self.P[ki, kj, n_p]
                                * hpt
                            ) / (self.rho * self.Cp * self.T_reserv * (self.c_r**2))
                            b_TH = (
                                self.speed
                                * self.mu_ref
                                * (hpt**2)
                                * 4
                                * mi_t
                                * self.dY
                                * self.dZ
                            ) / (self.rho * self.Cp * self.T_reserv * 3 * HP)
                            b_TI = (
                                auxb_T
                                * (mi_t * (self.R**2) * self.dY * self.dZ)
                                / (HP * self.c_r)
                            )
                            b_TJ = (
                                auxb_T
                                * (
                                    (self.R**2)
                                    * (HP**3)
                                    * (dPdy[ki, kj, n_p] ** 2)
                                    * self.dY
                                    * self.dZ
                                )
                                / (12 * self.c_r * (self.betha_s**2) * mi_t)
                            )
                            b_TK = (
                                auxb_T
                                * (
                                    (self.R**4)
                                    * (HP**3)
                                    * (dPdz[ki, kj, n_p] ** 2)
                                    * self.dY
                                    * self.dZ
                                )
                                / (12 * self.c_r * (self.L**2) * mi_t)
                            )

                            B_T = b_TG + b_TH + b_TI + b_TJ + b_TK

                            k = k + 1

                            b_T[k - 1, 0] = B_T

                            if ki == 0 and kj == 0:
                                Mat_coef_T[k - 1, k - 1] = AP + AS - AW
                                Mat_coef_T[k - 1, k] = AE
                                Mat_coef_T[k - 1, k + self.n_theta - 1] = AN
                                b_T[k - 1, 0] = b_T[k - 1, 0] - 2 * AW * (
                                    T_ref / self.T_reserv
                                )

                            elif kj == 0 and ki > 0 and ki < self.n_z - 1:
                                Mat_coef_T[k - 1, k - 1] = AP - AW
                                Mat_coef_T[k - 1, k] = AE
                                Mat_coef_T[k - 1, k - self.n_theta - 1] = AS
                                Mat_coef_T[k - 1, k + self.n_theta - 1] = AN
                                b_T[k - 1, 0] = b_T[k - 1, 0] - 2 * AW * (
                                    T_ref / self.T_reserv
                                )

                            elif kj == 0 and ki == self.n_z - 1:
                                Mat_coef_T[k - 1, k - 1] = AP + AN - AW
                                Mat_coef_T[k - 1, k] = AE
                                Mat_coef_T[k - 1, k - self.n_theta - 1] = AS
                                b_T[k - 1, 0] = b_T[k - 1, 0] - 2 * AW * (
                                    T_ref / self.T_reserv
                                )

                            elif ki == 0 and kj > 0 and kj < self.n_y - 1:
                                Mat_coef_T[k - 1, k - 1] = AP + AS
                                Mat_coef_T[k - 1, k] = AE
                                Mat_coef_T[k - 1, k - 2] = AW
                                Mat_coef_T[k - 1, k + self.n_theta - 1] = AN

                            elif (
                                ki > 0
                                and ki < self.n_z - 1
                                and kj > 0
                                and kj < self.n_y - 1
                            ):
                                Mat_coef_T[k - 1, k - 1] = AP
                                Mat_coef_T[k - 1, k - 2] = AW
                                Mat_coef_T[k - 1, k - self.n_theta - 1] = AS
                                Mat_coef_T[k - 1, k + self.n_theta - 1] = AN
                                Mat_coef_T[k - 1, k] = AE

                            elif ki == self.n_z - 1 and kj > 0 and kj < self.n_y - 1:
                                Mat_coef_T[k - 1, k - 1] = AP + AN
                                Mat_coef_T[k - 1, k] = AE
                                Mat_coef_T[k - 1, k - 2] = AW
                                Mat_coef_T[k - 1, k - self.n_theta - 1] = AS

                            elif ki == 0 and kj == self.n_y - 1:
                                Mat_coef_T[k - 1, k - 1] = AP + AE + AS
                                Mat_coef_T[k - 1, k - 2] = AW
                                Mat_coef_T[k - 1, k + self.n_theta - 1] = AN

                            elif kj == self.n_y - 1 and ki > 0 and ki < self.n_z - 1:
                                Mat_coef_T[k - 1, k - 1] = AP + AE
                                Mat_coef_T[k - 1, k - 2] = AW
                                Mat_coef_T[k - 1, k - self.n_theta - 1] = AS
                                Mat_coef_T[k - 1, k + self.n_theta - 1] = AN

                            elif ki == self.n_z - 1 and kj == self.n_y - 1:
                                Mat_coef_T[k - 1, k - 1] = AP + AE + AN
                                Mat_coef_T[k - 1, k - 2] = AW
                                Mat_coef_T[k - 1, k - self.n_theta - 1] = AS

                            kj = kj + 1

                        kj = 0
                        ki = ki + 1

                    # Solution of temperature field end

                    t = np.linalg.solve(Mat_coef_T, b_T)
                    cont = 0

                    for i in np.arange(self.n_z):
                        for j in np.arange(self.n_theta):

                            T_new[i, j, n_p] = t[cont]
                            cont = cont + 1

                    Tdim = T_new * self.T_reserv

                    T_end = np.sum(Tdim[:, -1, n_p]) / self.n_z

                    T_mist[n_p] = (
                        self.fat_mixt[n_p] * self.T_reserv
                        + (1 - self.fat_mixt[n_p]) * T_end
                    )

                    for i in np.arange(self.n_z):
                        for j in np.arange(self.n_theta):

                            mu_new[i, j, n_p] = (
                                self.a * (Tdim[i, j, n_p]) ** self.b
                            ) / self.mu_ref

        PP = np.zeros(((self.n_z), (self.n_pad * self.n_theta)))

        i = 0
        for i in range(self.n_z):

            PP[i] = self.Pdim[i, :, :].ravel("F")

        Ytheta = np.array(Ytheta)
        Ytheta = Ytheta.flatten()

        auxF = np.zeros((2, len(Ytheta)))

        auxF[0, :] = np.cos(Ytheta)
        auxF[1, :] = np.sin(Ytheta)

        dA = self.dy * self.dz

        auxP = PP * dA

        vector_auxF_x = auxF[0, :]
        vector_auxF_y = auxF[1, :]

        auxFx = auxP * vector_auxF_x
        auxFy = auxP * vector_auxF_y

        fxj = -np.sum(auxFx)
        fyj = -np.sum(auxFy)

        Fhx = fxj
        Fhy = fyj
        self.Fhx = Fhx
        self.Fhy = Fhy
        return Fhx, Fhy

    def run(self, x, print_result=False, print_progress=False, print_time=False):
        """This method runs the optimization to find the equilibrium position of the rotor's center.

        Parameters
        ----------
        x : array
            Array with eccentricity ratio and attitude angle
        print_progress : bool
            Set it True to print the score and forces on each iteration.
            False by default.
        """
        args = print_progress
        t1 = time.time()
        res = minimize(
            self._score,
            x,
            args,
            method="Nelder-Mead",
            tol=10e-3,
            options={"maxiter": 1000},
        )
        self.equilibrium_pos = res.x
        t2 = time.time()

        if print_result:
            print(res)

        if print_time:
            print(f"Time Spent: {t2-t1} seconds")

    def _interpol(self, T_muI, T_muF, mu_I, mu_F):
        """

        Parameters
        ----------



        Returns
        -------

        """

        def viscosity(x, a, b):
            return a * (x**b)

        xdata = [T_muI, T_muF]  # changed boundary conditions to avoid division by ]
        ydata = [mu_I, mu_F]

        popt, pcov = curve_fit(viscosity, xdata, ydata, p0=(6.0, -1.0))
        a, b = popt

        return a, b

    def coefficients(self, method="lund", show_coef=True):
        """Calculates the dynamic coefficients of stiffness "k" and damping "c". The formulation is based in application of virtual displacements and speeds on the rotor from its equilibrium position to determine the bearing stiffness and damping coefficients.

        Parameters
        ----------
        method : string
            Choose the method of ... Options are:
                lund: method that calculates...
                perturbation: method that ...
        show_coef : bool
            Set it True, to print the calculated coefficients.
            False by default.

        Returns
        -------
        coefs : tuple
            Bearing stiffness and damping coefficients.
            Its shape is: ((kxx, kxy, kyx, kyy), (cxx, cxy, cyx, cyy))

        """
        if self.equilibrium_pos is None:
            self.run([0.1, -0.1], True, True)
            self.coefficients(method=method,show_coef=show_coef)
        else:
            if method ==  "lund":
                k,c = self._lund_method()
            elif method == "perturbation":
                k,c = self._pertubation_method()
                
            if show_coef:
                print(f"kxx = {k[0]}")
                print(f"kxy = {k[1]}")
                print(f"kyx = {k[2]}")
                print(f"kyy = {k[3]}")

                print(f"cxx = {c[0]}")
                print(f"cxy = {c[1]}")
                print(f"cyx = {c[2]}")
                print(f"cyy = {c[3]}")

            coefs = (k,c)

            return coefs
        
    def _pertubation_method(self):
        """perturbation method explain

        """
        
        xeq = self.equilibrium_pos[0] * self.c_r * np.cos(self.equilibrium_pos[1])
        yeq = self.equilibrium_pos[0] * self.c_r * np.sin(self.equilibrium_pos[1])

        dE = 0.001
        epix = np.abs(dE * self.c_r * np.cos(self.equilibrium_pos[1]))
        epiy = np.abs(dE * self.c_r * np.sin(self.equilibrium_pos[1]))

        Va = self.speed * (self.R)
        epixpt = 0.000001 * np.abs(Va * np.sin(self.equilibrium_pos[1]))
        epiypt = 0.000001 * np.abs(Va * np.cos(self.equilibrium_pos[1]))

        Aux01 = self._forces(xeq + epix, yeq, 0, 0)
        Aux02 = self._forces(xeq - epix, yeq, 0, 0)
        Aux03 = self._forces(xeq, yeq + epiy, 0, 0)
        Aux04 = self._forces(xeq, yeq - epiy, 0, 0)

        Aux05 = self._forces(xeq, yeq, epixpt, 0)
        Aux06 = self._forces(xeq, yeq, -epixpt, 0)
        Aux07 = self._forces(xeq, yeq, 0, epiypt)
        Aux08 = self._forces(xeq, yeq, 0, -epiypt)

        # Ss = self.sommerfeld(Aux08[0],Aux08[1])

        Kxx = -self.sommerfeld(Aux01[0], Aux02[1]) * (
            (Aux01[0] - Aux02[0]) / (epix / self.c_r)
        )
        Kxy = -self.sommerfeld(Aux03[0], Aux04[1]) * (
            (Aux03[0] - Aux04[0]) / (epiy / self.c_r)
        )
        Kyx = -self.sommerfeld(Aux01[1], Aux02[1]) * (
            (Aux01[1] - Aux02[1]) / (epix / self.c_r)
        )
        Kyy = -self.sommerfeld(Aux03[1], Aux04[1]) * (
            (Aux03[1] - Aux04[1]) / (epiy / self.c_r)
        )

        Cxx = -self.sommerfeld(Aux05[0], Aux06[0]) * (
            (Aux06[0] - Aux05[0]) / (epixpt / self.c_r / self.speed)
        )
        Cxy = -self.sommerfeld(Aux07[0], Aux08[0]) * (
            (Aux08[0] - Aux07[0]) / (epiypt / self.c_r / self.speed)
        )
        Cyx = -self.sommerfeld(Aux05[1], Aux06[1]) * (
            (Aux06[1] - Aux05[1]) / (epixpt / self.c_r / self.speed)
        )
        Cyy = -self.sommerfeld(Aux07[1], Aux08[1]) * (
            (Aux08[1] - Aux07[1]) / (epiypt / self.c_r / self.speed)
        )

        kxx = (np.sqrt((self.Wx**2) + (self.Wy**2)) / self.c_r) * Kxx
        kxy = (np.sqrt((self.Wx**2) + (self.Wy**2)) / self.c_r) * Kxy
        kyx = (np.sqrt((self.Wx**2) + (self.Wy**2)) / self.c_r) * Kyx
        kyy = (np.sqrt((self.Wx**2) + (self.Wy**2)) / self.c_r) * Kyy

        cxx = (
            np.sqrt((self.Wx**2) + (self.Wy**2)) / (self.c_r * self.speed)
        ) * Cxx
        cxy = (
            np.sqrt((self.Wx**2) + (self.Wy**2)) / (self.c_r * self.speed)
        ) * Cxy
        cyx = (
            np.sqrt((self.Wx**2) + (self.Wy**2)) / (self.c_r * self.speed)
        ) * Cyx
        cyy = (
            np.sqrt((self.Wx**2) + (self.Wy**2)) / (self.c_r * self.speed)
        ) * Cyy
        
        return (kxx,kxy,kyx,kyy),(cxx,cxy,cyx,cyy)
    
    def _lund_method(self):
        """Calculates the dynamic coefficients of stiffness "k" and damping "c". A small amplitude whirl of the journal center (a first order perturbation solution) is aplied. 
        The four stiffness coefficients, and the four damping coefficients is obtained by integration of the pressure field. 


        """
            
        p = self.P
 
        x0 = self.equilibrium_pos

        dZ=1/self.n_z
  
        Z1=0        #initial coordinate z dimensionless
        Z2=1
        Z = np.arange(Z1+0.5*dZ,Z2,dZ) #vector z dimensionless
        Zdim=Z*self.L

   
        Ytheta = np.zeros((self.n_pad,self.n_theta))
        
        # Dimensionless
        xr = x0[0] * self.c_r * np.cos(x0[1])  # Representa a posição do centro do eixo ao longo da direção "Y"
        yr = x0[0] * self.c_r * np.sin(x0[1])  # Representa a posição do centro do eixo ao longo da direção "X"
        Y = yr/self.c_r                        # Representa a posição em x adimensional
        X = xr/self.c_r    

        nk=(self.n_z)*(self.n_theta)
        
        gamma = 0.001 #Frequencia da perturbação sobre velocidade de rotação
        
        wp = gamma*self.speed
        
        Mat_coef=np.zeros((nk,nk))
        
        bX=np.zeros((nk,1)).astype(complex)
        
        bY=np.zeros((nk,1)).astype(complex)
        
        hX = np.zeros((self.n_pad,self.n_theta))
        
        hY = np.zeros((self.n_pad,self.n_theta))
        
        PX=np.zeros((self.n_z,self.n_theta,self.n_pad)).astype(complex)
        
        PY=np.zeros((self.n_z,self.n_theta,self.n_pad)).astype(complex)
        
        H=np.zeros((2,2)).astype(complex)
        
        n_p = 0
        
        for n_p in np.arange(self.n_pad):
            
            Ytheta[n_p,:] = np.arange(self.thetaI[n_p]+(self.dtheta/2),self.thetaF[n_p],self.dtheta)
            
            ki=0
            kj=0
            
            k=0 #vectorization pressure index
            
            for ii in np.arange((self.Z_I + 0.5 * self.dZ), self.Z_F, self.dZ):
                for jj in np.arange(self.thetaI[n_p] + (self.dtheta / 2),self.thetaF[n_p],self.dtheta):

                     
                    hP=1-X*np.cos(jj)-Y*np.sin(jj)                
                    he=1-X*np.cos(jj+0.5*self.dtheta)-self.Y*np.sin(jj+0.5*self.dtheta)
                    hw=1-X*np.cos(jj-0.5*self.dtheta)-self.Y*np.sin(jj-0.5*self.dtheta)
                    hn=hP
                    hs=hn
                    
                    hXP = -np.cos(jj)
                    hXe = -np.cos(jj+0.5*self.dtheta)
                    hXw = -np.cos(jj-0.5*self.dtheta)
                    hXn = hXP
                    hXs = hXn
                    
                    hYP = -np.sin(jj)
                    hYe = -np.sin(jj+0.5*self.dtheta)
                    hYw = -np.sin(jj-0.5*self.dtheta)
                    hYn = hYP
                    hYs = hYn
                    
                    if ki==0:
                        hX[n_p,kj] = hXP
                        hY[n_p,kj] = hYP
                    
                    
                
                    if kj==0 and ki==0:
                        MU_e = 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki,kj+1,n_p])
                        MU_w = self.mu_l[ki,kj,n_p]
                        MU_s = self.mu_l[ki,kj,n_p]
                        MU_n = 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki+1,kj,n_p])
                        
                        pE= p[ki,kj+1,n_p]
                        pW= -p[ki,kj,n_p]
                        pN= p[ki+1,kj,n_p]
                        pS= -p[ki,kj,n_p]
                  
                
                    if kj==0 and ki>0 and ki<self.n_z-1:
                        MU_e= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki,kj+1,n_p])
                        MU_w= self.mu_l[ki,kj,n_p]
                        MU_s= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki-1,kj,n_p])
                        MU_n= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki+1,kj,n_p])
                        
                        pE= p[ki,kj+1,n_p]
                        pW= -p[ki,kj,n_p]
                        pN= p[ki+1,kj,n_p]
                        pS= p[ki-1,kj,n_p]
                  
                
                    if kj==0 and ki==self.n_z-1:
                        MU_e= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki,kj+1,n_p])
                        MU_w= self.mu_l[ki,kj,n_p]
                        MU_s= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki-1,kj,n_p])
                        MU_n= self.mu_l[ki,kj,n_p]
                        
                        pE= p[ki,kj+1,n_p]
                        pW= -p[ki,kj,n_p]
                        pN= -p[ki,kj,n_p]
                        pS= p[ki-1,kj,n_p]
                   
                
                    if ki==0 and kj>0 and kj<self.n_theta-1:
                        MU_e= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki,kj+1,n_p])
                        MU_w= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki,kj-1,n_p])
                        MU_s= self.mu_l[ki,kj,n_p]
                        MU_n= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki+1,kj,n_p])
                        
                        pE= p[ki,kj+1,n_p]
                        pW= p[ki,kj-1,n_p]
                        pN= p[ki+1,kj,n_p]
                        pS= -p[ki,kj,n_p]
                
                
                    if kj>0 and kj<self.n_theta-1 and ki>0 and ki<self.n_z-1:
                        MU_e= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki,kj+1,n_p])
                        MU_w= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki,kj-1,n_p])
                        MU_s= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki-1,kj,n_p])
                        MU_n= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki+1,kj,n_p])
            
                        pE= p[ki,kj+1,n_p]
                        pW= p[ki,kj-1,n_p]
                        pN= p[ki+1,kj,n_p]
                        pS= p[ki-1,kj,n_p]
                
                
                    if ki==self.n_z-1 and kj>0 and kj<self.n_theta-1:
                        MU_e= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki,kj+1,n_p])
                        MU_w= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki,kj-1,n_p])
                        MU_s= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki-1,kj,n_p])
                        MU_n= self.mu_l[ki,kj,n_p]
                        
                        pE= p[ki,kj+1,n_p]
                        pW= p[ki,kj-1,n_p]
                        pN= -p[ki,kj,n_p]
                        pS= p[ki-1,kj,n_p]
                   
                
                    if ki==0 and kj==self.n_theta-1:
                        MU_e= self.mu_l[ki,kj,n_p]
                        MU_w= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki,kj-1,n_p])
                        MU_s= self.mu_l[ki,kj,n_p]
                        MU_n= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki+1,kj,n_p])
                        
                        pE= -p[ki,kj,n_p]
                        pW= p[ki,kj-1,n_p]
                        pN= p[ki+1,kj,n_p]
                        pS= -p[ki,kj,n_p]
                  
                
                    if kj==self.n_theta-1 and ki>0 and ki<self.n_z-1:
                        MU_e= self.mu_l[ki,kj,n_p]
                        MU_w= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki,kj-1,n_p])
                        MU_s= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki-1,kj,n_p])
                        MU_n= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki+1,kj,n_p])
                
                        pE= -p[ki,kj,n_p]
                        pW= p[ki,kj-1,n_p]
                        pN= p[ki+1,kj,n_p]
                        pS= p[ki-1,kj,n_p]
                
                
                    if kj==self.n_theta-1 and ki==self.n_z-1:
                        MU_e= self.mu_l[ki,kj,n_p]
                        MU_w= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki,kj-1,n_p])
                        MU_s= 0.5*(self.mu_l[ki,kj,n_p]+self.mu_l[ki-1,kj,n_p])
                        MU_n= self.mu_l[ki,kj,n_p]
                
                        pE= -p[ki,kj,n_p]
                        pW= p[ki,kj-1,n_p]
                        pN= -p[ki,kj,n_p]
                        pS= p[ki-1,kj,n_p]
                
                    pP=p[ki,kj,n_p]
                    
                    CE=(self.dZ*he**3)/(12*MU_e*self.dY*self.betha_s**2)
                    CW=(self.dZ*hw**3)/(12*MU_w*self.dY*self.betha_s**2)
                    CN=(self.dY*(self.R**2)*hn**3)/(12*MU_n*self.dZ*self.L**2)
                    CS=(self.dY*(self.R**2)*hs**3)/(12*MU_s*self.dZ*self.L**2)
                    
                    CP=-(CE+CW+CN+CS)
                    
                    BXE = -(self.dZ/(self.dY*self.betha_s**2))*((3*he**2*hXe)/(12*MU_e))
                    
                    BYE = -(self.dZ/(self.dY*self.betha_s**2))*((3*he**2*hYe)/(12*MU_e))
                    
                    BXW = -(self.dZ/(self.dY*self.betha_s**2))*((3*hw**2*hXw)/(12*MU_w))
                    
                    BYW = -(self.dZ/(self.dY*self.betha_s**2))*((3*hw**2*hYw)/(12*MU_w))
                    
                    BXN = -((self.R**2)*self.dY/(self.dZ*self.L**2))*((3*hn**2*hXn)/(12*MU_n))
                    
                    BYN = -((self.R**2)*self.dY/(self.dZ*self.L**2))*((3*hn**2*hYn)/(12*MU_n))
                    
                    BXS = -((self.R**2)*self.dY/(self.dZ*self.L**2))*((3*hs**2*hXs)/(12*MU_s))
                    
                    BYS = -((self.R**2)*self.dY/(self.dZ*self.L**2))*((3*hs**2*hYs)/(12*MU_s))
                    
                    BXP = -(BXE+BXW+BXN+BXS)
                    
                    BYP = -(BYE+BYW+BYN+BYS)
                    
                    BX=(self.dZ/(2*self.betha_s))*(hXe-hXw)+(self.dY*self.dZ*1j*gamma*hXP)+BXE*pE+BXW*pW+BXN*pN+BXS*pS+BXP*pP
                    
                    BY=(self.dZ/(2*self.betha_s))*(hYe-hYw)+(self.dY*self.dZ*1j*gamma*hYP)+BYE*pE+BYW*pW+BYN*pN+BYS*pS+BYP*pP
            
                    k=k+1
                    bX[k-1,0]=BX
                    bY[k-1,0]=BY
                
                    if ki==0 and kj==0:
                        Mat_coef[k-1,k-1]=CP-CS-CW
                        Mat_coef[k-1,k]=CE
                        Mat_coef[k-1,k+self.n_theta-1]=CN
                   
                    
                    elif kj==0 and ki>0 and ki<self.n_z-1:
                        Mat_coef[k-1,k-1]=CP-CW
                        Mat_coef[k-1,k]=CE
                        Mat_coef[k-1,k-self.n_theta-1]=CS
                        Mat_coef[k-1,k+self.n_theta-1]=CN
                        
                    elif kj==0 and ki==self.n_z-1:
                        Mat_coef[k-1,k-1]=CP-CN-CW
                        Mat_coef[k-1,k]=CE
                        Mat_coef[k-1,k-self.n_theta-1]=CS 
                
                
                    elif ki==0 and kj>0 and kj<self.n_theta-1:
                        Mat_coef[k-1,k-1]=CP-CS
                        Mat_coef[k-1,k]=CE
                        Mat_coef[k-1,k-2]=CW
                        Mat_coef[k-1,k+self.n_theta-1]=CN
                  
                    
                    if ki>0 and ki<self.n_z-1 and kj>0 and kj<self.n_theta-1:
                        Mat_coef[k-1,k-1]=CP
                        Mat_coef[k-1,k-2]=CW
                        Mat_coef[k-1,k-self.n_theta-1]=CS
                        Mat_coef[k-1,k+self.n_theta-1]=CN
                        Mat_coef[k-1,k]=CE
                    
                    
                    elif ki==self.n_z-1 and kj>0 and kj<self.n_theta-1:
                        Mat_coef[k-1,k-1]=CP-CN
                        Mat_coef[k-1,k]=CE
                        Mat_coef[k-1,k-2]=CW
                        Mat_coef[k-1,k-self.n_theta-1]=CS
                       
                        
                    elif ki==0 and kj==self.n_theta-1:
                        Mat_coef[k-1,k-1]=CP-CE-CS
                        Mat_coef[k-1,k-2]=CW
                        Mat_coef[k-1,k+self.n_theta-1]=CN
                        
                        
                    elif kj==self.n_theta-1 and ki>0 and ki<self.n_z-1:
                        Mat_coef[k-1,k-1]=CP-CE
                        Mat_coef[k-1,k-2]=CW
                        Mat_coef[k-1,k-self.n_theta-1]=CS
                        Mat_coef[k-1,k+self.n_theta-1]=CN       
                  
                                   
                    elif ki==self.n_z-1 and kj==self.n_theta-1:
                        Mat_coef[k-1,k-1]=CP-CE-CN
                        Mat_coef[k-1,k-2]=CW
                        Mat_coef[k-1,k-self.n_theta-1]=CS
                     
                    kj=kj+1
                   
                kj=0
                ki=ki+1
                   
                #    ###################### Solution of pressure field #######################
                
            pX=np.linalg.solve(Mat_coef,bX)
            
            pY=np.linalg.solve(Mat_coef,bY)
            
            cont=0
            
            for i in np.arange(self.n_z):
                for j in np.arange(self.n_theta):
                    
                    PX[i,j,n_p]=pX[cont]
                    PY[i,j,n_p]=pY[cont]
                    cont=cont+1
        
        PPlotX=np.zeros((self.n_z,self.n_theta*self.n_pad)).astype(complex)
        PPlotY=np.zeros((self.n_z,self.n_theta*self.n_pad)).astype(complex)
        
        i = 0
        for i in range(self.n_z):
            
            PPlotX[i]=PX[i,:,:].ravel('F')
            PPlotY[i]=PY[i,:,:].ravel('F')
        
        
        Ytheta = Ytheta.flatten()
        
        
        PPlotXdim = PPlotX*(self.mu_ref*self.speed*(self.R**2))/(self.c_r**3)
        
        PPlotYdim = PPlotY*(self.mu_ref*self.speed*(self.R**2))/(self.c_r**3)
        
        hX = hX.flatten()
        hY = hY.flatten()
        
        aux_intXX = PPlotXdim*hX.T
        
        aux_intXY = PPlotXdim*hY.T
        
        aux_intYX = PPlotYdim*hX.T
        
        aux_intYY = PPlotYdim*hY.T
        
        H[0,0] = -np.trapz(np.trapz(aux_intXX,Ytheta*self.R),Zdim)
        
        H[0,1] = -np.trapz(np.trapz(aux_intXY,Ytheta*self.R),Zdim)
        
        H[1,0] = -np.trapz(np.trapz(aux_intYX,Ytheta*self.R),Zdim)
        
        H[1,1] = -np.trapz(np.trapz(aux_intYY,Ytheta*self.R),Zdim)
        
        K = np.real(H)
        C = np.imag(H)/wp
        
        kxx=K[0,0]
        kxy=K[0,1]
        kyx=K[1,0]
        kyy=K[1,1]
        
        
        cxx=C[0,0]
        cxy=C[0,1]
        cyx=C[1,0]
        cyy=C[1,1]
        
        return (kxx,kxy,kyx,kyy),(cxx,cxy,cyx,cyy)           

    def _score(self, x, print_progress=False):
        """This method used to set the objective function of minimize optimization.

        Parameters
        ==========
        score: float
           Balanced Force expression between the load aplied in bearing and the
           resultant force provide by oil film.

        Returns
        ========
        Score coefficient.

        """
        Fhx, Fhy = self._forces(x, None, None, None)
        score = np.sqrt(((self.Wx + Fhx) ** 2) + ((self.Wy + Fhy) ** 2))
        if print_progress:
            print(f"Score: ", score)
            print("============================================")
            print(f"Força na direção x: ", Fhx)
            print("============================================")
            print(f"Força na direção y: ", Fhy)
            print("")

        return score

    def sommerfeld(self, force_x, force_y):
        """Calculate the sommerfeld number. This dimensionless number is used to calculate the dynamic coeficients.

        Parameters
        ----------
        force_x : float
            Force in x direction. The unit is newton.
        force_y : float
            Force in y direction. The unit is newton.

        Returns
        -------
        Ss : float
            Sommerfeld number.
        """
        if self.sommerfeld_type == 1:
            S = (self.mu_ref * ((self.R) ** 3) * self.L * self.speed) / (
                np.pi * (self.c_r**2) * np.sqrt((self.Wx**2) + (self.Wy**2))
            )

        elif self.sommerfeld_type == 2:
            S = 1 / (
                2
                * ((self.L / (2 * self.R)) ** 2)
                * (np.sqrt((force_x**2) + (force_y**2)))
            )

        Ss = S * ((self.L / (2 * self.R)) ** 2)

        return Ss


def cylindrical_bearing_example():
    """Create an example of a cylindrical bearing with termo hydrodynamic effects. This function returns pressure and temperature field and dynamic coefficient. The purpose is to make available a simple model so that a doctest can be written using it.
    Returns
    -------
    THDCylindrical : ross.THDCylindrical Object
        An instance of a termo-hydrodynamic cylendrical bearing model object.
    Examples
    --------
    >>> bearing = cylindrical_bearing_example()
    >>> bearing.L
    0.263144
    """

    bearing = THDCylindrical(
        L=0.263144,
        R=0.2,
        c_r=1.95e-4,
        n_theta=11,
        n_z=3,
        n_y=None,
        betha_s=176,
        mu_ref=0.02,
        speed=Q_(900, "RPM"),
        Wx=0,
        Wy=-112814.91,
        k_t=0.15327,
        Cp=1915.24,
        rho=854.952,
        T_reserv=50,
        fat_mixt=[0.52, 0.48],
        T_muI=50,
        T_muF=80,
        mu_I=0.02,
        mu_F=0.01,
        sommerfeld_type=2,
    )

    return bearing

if __name__ == "__main__":
    
    x0 = [0.1,-0.1]
    bearing = cylindrical_bearing_example()
    bearing.run(x0)
    bearing.coefficients(method="lund")
    bearing.equilibrium_pos()