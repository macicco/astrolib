# -*- coding: utf-8 -*-

from astropy.io import fits
from astropy.wcs import WCS
from astropy import coordinates
from astropy import units as u
# from astropy.time import Time
# from astropy.time import TimeDelta
from astropy.table import Table
from .catalog import Query
from .astronomy import FitsOps
from .astronomy import AstCalc
from .astronomy import TimeOps
import sep
import math
import numpy as np
import os
import glob
import time
import matplotlib.pyplot as plt
from .peakdetect import peakdet

try:
    import f2n
except ImportError:
    print('Python cannot import f2n. Make sure f2n is installed.')
    raise SystemExit


class PhotOps:

    def update_progress(self, job_title, progress):

        """
        Update for progress.
        @param job_title: Progress bar's title.
        @type job_title: str
        @param progress: Progress bar's status value.
        @type progres: int
        @return: str
        """

        length = 20
        block = int(round(length * progress))
        msg = "\r{0}: [{1}] {2}%".format(job_title,
                                         "#"*block + "-"*(length-block),
                                         round(progress*100, 2))
        if progress >= 1:
            msg += "\nDONE\r\n"

        print(msg)
        
    def phot(self, image_path,
             x_coor, y_coor,
             aper_radius=3.0,
             gain=0.57):

        """
        Photometry of given coordinates.
        @param image_path: Path of FITS file.
        @type image_path: path
        @param x_coor: X coordinate of object
        @type x_coor: float
        @param y_coor: Y coordinate of object
        @type y_coor: float
        @param aper_radius: Aperture radius
        @type aper_radius: float
        @return: tuple
        """
        
        if image_path:
            hdu = fits.open(image_path)[0]
        else:
            print("FITS image has not been provided by the user!")
            raise SystemExit

        data = hdu.data.astype(float)

        bkg = sep.Background(data)
        # bkg_image = bkg.back()
        # bkg_rms = bkg.rms()
        data_sub = data - bkg

        flux, fluxerr, flag = sep.sum_circle(data_sub,
                                             x_coor,
                                             y_coor,
                                             aper_radius=aper_radius,
                                             err=bkg.globalrms,
                                             gain=gain)

        return({"flag": flag,
                "flux": flux,
                "fluxerr": fluxerr})

    def asteroids_phot(self, image_path,
                       multi_object=True,
                       target=None,
                       aper_radius=None,
                       plot_aper_test=False,
                       radius=11, gain=0.57, max_mag=20):

        """
        Photometry of asteroids.
        @param image_path: Path of FITS file.
        @type image_path: path
        @param multi_object: Apply photometry for other asteroids in the frame?
        @type multi_object: float
        @param target: Target object that photometry applied. If None,
        will be taken form FITS header.
        @type target: float
        @param aper_radius: Aperture radius
        @type aper_radius: float
        @param plot_aper_test: Plot aperture test graph
        @type plot_aper_test: bloean
        @param gain: gain value for the image expressed in electrons per adu.
        @type gain: float
        @param max_mag: Faintest object limit.
        @type max_mag: float
        @return: bolean and file
        """
        
        if ".fit" in os.path.basename(image_path):
            fitslist = sorted(glob.glob(image_path))
            if fitslist == 0:
                print('No image FITS found in the {0}'.format(image_path))
                raise SystemExit
        else:
            fitslist = sorted(glob.glob(image_path + '/*.fit?'))
            if fitslist == 0:
                print('No image FITS found in the {0}'.format(image_path))
                raise SystemExit

        for id, fitsfile in enumerate(fitslist):
            if fitsfile:
                hdu = fits.open(fitsfile)[0]
            else:
                print("FITS image has not been provided by the user!")
                raise SystemExit

            sb = Query()
            ac = AstCalc()
            to = TimeOps()
            fo = FitsOps(fitsfile)
            header = hdu.header
            w = WCS(header)

            naxis1 = fo.get_header('naxis1')
            naxis2 = fo.get_header('naxis2')
            odate = fo.get_header('date-obs')
            if target is None:
                objct = fo.get_header('object')
            else:
                objct = str(target)
            filter = fo.get_header('filter').replace(" ", "_")
            # t1 = Time(odate.replace('T', ' '))
            # exptime = fo.get_header('exptime')
            # dt = TimeDelta(exptime / 2.0, format='sec')
            # odate_middle = t1 + dt
            # jd = to.date2jd(odate_middle.value)
            jd = to.date2jd(odate)
            ra_dec = ac.center_finder(fitsfile, wcs_ref=True)

            image = f2n.fromfits(fitsfile, verbose=False)
            image.setzscale('auto', 'auto')
            image.makepilimage('log', negative=False)

            request = sb.find_skybot_objects(odate,
                                             ra_dec[0].degree,
                                             ra_dec[1].degree,
                                             radius=radius)

            if request[0]:
                if multi_object:
                    asteroids = Table(np.sort(request[1][::-1],
                                              order=['m_v']))
                else:
                    asteroids = Table(np.sort(request[1],
                                              order=['num']))
                    mask = asteroids['num'] == str(objct).upper()
                    asteroids = asteroids[mask]
            elif request[0] is False:
                print(request[1])
                raise SystemExit

            data = hdu.data.astype(float)

            bkg = sep.Background(data)
            data_sub = data - bkg

            for i in range(len(asteroids)):
                if float(asteroids['m_v'][i]) <= max_mag:
                    c = coordinates.SkyCoord('{0} {1}'.format(
                        asteroids['ra(h)'][i],
                        asteroids['dec(deg)'][i]),
                                             unit=(u.hourangle, u.deg),
                                             frame='icrs')

                    # asteroid's X and Y coor
                    a_x, a_y = w.wcs_world2pix(c.ra.degree, c.dec.degree, 1)

                    if naxis1 < a_x or naxis2 < a_y or a_x < 0 or a_y < 0:
                        continue

                    # phot asteroids
                    flux, fluxerr, flag = sep.sum_circle(
                        data_sub,
                        a_x,
                        a_y,
                        6,
                        err=bkg.globalrms,
                        gain=gain)

                    if flux == 0.0 or fluxerr == 0.0:
                        print("Bad asteroid selected (out of frame!)!")
                        raise SystemExit

                    if id == 0:
                        snr = []
                        for aper in range(30):
                            # phot asteroids
                            flux_test, fluxerr_test, flag_test = sep.sum_circle(
                                data_sub,
                                a_x,
                                a_y,
                                aper,
                                err=bkg.globalrms,
                                gain=gain)

                            snr.append([aper, (flux_test/fluxerr_test)])

                        npsnr = np.array(snr)
                        maxtab, mintab = peakdet(npsnr[:, 1], 0.1)
                        aper_radius = maxtab[:, 0][0]
                        print("Aperture calculated: {0} px".format(
                            aper_radius))
                        
                        if plot_aper_test:
                            plt.title(asteroids['num'][i])
                            plt.xlabel('Aperture (px)')
                            plt.ylabel('SNR')
                            
                            plt.scatter(npsnr[:, 0],
                                        npsnr[:, 1])
                            plt.scatter(maxtab[:, 0], maxtab[:, 1],
                                        color='red')
                            plt.scatter(mintab[:, 0], mintab[:, 1],
                                        color='yellow')
                            plt.show()

                    magt_i = ac.flux2mag(flux)
                    magt_i_err = fluxerr / flux * 2.5 / math.log(10)

                    min_mag_ast = float(asteroids['m_v'][i]) - 2

                    label = '{0}'.format(asteroids['num'][i])
                    image.drawcircle(a_x, a_y, r=aper_radius,
                                     colour=(255, 0, 0), label=label)

                    if i < 1 and id < 1:
                        comptable = sb.query_color(c.ra.degree,
                                                   c.dec.degree,
                                                   5.0 / 60.0,
                                                   min_mag=min_mag_ast,
                                                   max_mag=19.5)

                        s_comptable = sb.sort_stars(comptable, min_mag_ast)

                    phot_res_list = []

                    # phot comp. stars
                    for j in range(len(s_comptable)):
                        # star's X and Y coor
                        s_x, s_y = w.wcs_world2pix(s_comptable['RAJ2000'][j],
                                                   s_comptable['DEJ2000'][j],
                                                   1)

                        if naxis1 < s_x or naxis2 < s_y or s_x < 0 or s_y < 0:
                            continue

                        # print('Circle', s_x, s_y, 10)

                        flux, fluxerr, flag = sep.sum_circle(
                            data_sub,
                            s_x,
                            s_y,
                            aper_radius,
                            err=bkg.globalrms,
                            gain=gain)

                        if flux == 0.0 or fluxerr == 0.0:
                            print("Bad star selected!")
                            raise SystemExit
                    
                        magc_i = ac.flux2mag(flux)
                        magc_i_err = fluxerr / flux * 2.5 / math.log(10)

                        try:
                            magt = (float(magt_i) -
                                    float(magc_i)) + s_comptable['Rmag'][j]
                            magt_err = math.sqrt(
                                math.pow(float(magt_i_err), 2) +
                                math.pow(float(magc_i_err), 2))
                        except:
                            continue

                        label = '{0}'.format(s_comptable['NOMAD1'][j])
                        image.drawcircle(s_x, s_y, r=aper_radius,
                                         colour=(0, 255, 0), label=label)

                        phot_res_list.append([asteroids['num'][i],
                                              jd,
                                              float(magt_i),
                                              float(magt_i_err),
                                              float(magc_i),
                                              float(magc_i_err),
                                              float(magt),
                                              float(magt_err),
                                              asteroids['m_v'][i],
                                              s_comptable['NOMAD1'][j],
                                              s_comptable['Rmag'][j]])

                    np_phot_res = np.array(phot_res_list)

                    if len(np_phot_res) == 0:
                        continue

                    # magnitude average
                    mag_t_avr = np.average(np_phot_res[:, 6].astype(float),
                                           weights=np_phot_res[:, 7].astype(
                                               float))

                    # mag_t_std calc.
                    mag_t_std = np.std(np_phot_res[:, 6].astype(float))
                    
                    np_mag_t_avr_std = [[mag_t_avr,
                                         mag_t_std,
                                         filter] for i in range(
                        len(np_phot_res))]
                    
                    k = np.array(np_mag_t_avr_std).reshape(
                        len(np_mag_t_avr_std), 3)

                    # numpy array with mag_t_avr
                    np_phot_res_avg_std = np.concatenate(
                        (np_phot_res,
                         k),
                        axis=1)

                    phot_res_table = Table(np_phot_res_avg_std,
                                           names=('ast_num',
                                                  'jd',
                                                  'magt_i',
                                                  'magt_i_err',
                                                  'magc_i',
                                                  'magc_i_err',
                                                  'magt',
                                                  'magt_err',
                                                  'ast_mag_cat',
                                                  'nomad1',
                                                  'star_Rmag',
                                                  'mag_t_avr',
                                                  'mag_t_std',
                                                  'filter'),
                                           dtype=('i4',
                                                  'S25',
                                                  'f8',
                                                  'f8',
                                                  'f8',
                                                  'f8',
                                                  'f8',
                                                  'f8',
                                                  'f8',
                                                  'U20',
                                                  'f8',
                                                  'f8',
                                                  'f8',
                                                  'U20'))

                    phot_res_table['magt_i'].format = '.3f'
                    phot_res_table['magt_i_err'].format = '.3f'
                    phot_res_table['magc_i'].format = '.3f'
                    phot_res_table['magc_i_err'].format = '.3f'
                    phot_res_table['magt'].format = '.3f'
                    phot_res_table['magt_err'].format = '.3f'
                    
                    with open('{0}/{1}.txt'.format(
                            os.getcwd(),
                            asteroids['num'][i]), 'a') as f_handle:
                        f_handle.seek(0, os.SEEK_END)

                        if not os.path.isfile(str(f_handle)):
                            phot_res_table.write(
                                f_handle,
                                format='ascii.commented_header')
                        else:
                            phot_res_table.write(f_handle,
                                                 format='ascii.no_header')

            # Test
            time.sleep(0.2)
            self.update_progress(
                "Photometry is done for: {0}".format(fitsfile),
                id / len(fitslist))
            image.writetitle(os.path.basename(fitsfile))

            fitshead, fitsextension = os.path.splitext(fitsfile)
            image.writeinfo([odate], colour=(255, 100, 0))
            image.tonet('{0}.png'.format(fitshead))
        self.update_progress("Photometry done!", 1)
        return(True)
