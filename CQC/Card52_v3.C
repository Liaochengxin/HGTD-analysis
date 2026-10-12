// This script is for analyzing 15x1 probe card test data of the wafer.
// The author is lazy, and he highly trust in your wisdom that you can understand the code.
// Please feel free to contact him if you have any questions.
// xxs:simple, only summarizations

//Weiyi Sun, IHEP  sunwy@ihep.ac.cn
//Primary function of the code: 
//Adjust the range of Vbd acceptance criterial based on test temperature; 
//for the 15×1 IV test data, apply the corresponding 0.8×Vbd to each IV curve → Lkg ratio under different Vbd values.
//-----------------------------------------------

//-----------------2025.11.12--------------------
//Tianyuan Zhang, IHEP, tyzhang@ihep.ac.cn
//Resolved several bugs present in the previous generation of code and provided more comprehensive and precise judgement criteria.
//Primary function of the code:
//Adjust the measured Vbd to the value corresponding to a test temperature of 20°C, and provide the Vbdmin value corresponding to 20°C.
//The IV curve continues to use actual data;
//For the 15×1 test data, using 0.8×Vbdmin at test temprature, determine the lkg max and lkg min for one main sensor -> lkg ratio at the same vbd
//For the 15×1 test data, using 0.8×Vbdmin at 20°C, determine the lkg max and lkg min for one main sensor -> lkg ratio at the same vbd



#include <TH2.h>
#include <TGraph.h>
#include <TStyle.h>
#include <TCanvas.h>
#include <TDirectory.h>
#include <TFile.h>
#include <TSystem.h>
#include <TTree.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include <fstream>
#include <string>
#include <sstream>
#include <stdexcept>
#include <stdlib.h>

using namespace ROOT::Math;

void CQCGetWaferMapOffset(int sensor, int &xOffset, int &yOffset) {
    if (sensor >= 1 && sensor <= 4) {
        xOffset = (sensor - 1) * 15 + 30;
        yOffset = 0;
    } else if (sensor >= 5 && sensor <= 10) {
        xOffset = 15 + (10 - sensor) * 15;
        yOffset = 15;
    } else if (sensor >= 11 && sensor <= 18) {
        xOffset = (sensor - 11) * 15;
        yOffset = 30;
    } else if (sensor >= 19 && sensor <= 26) {
        xOffset = (26 - sensor) * 15;
        yOffset = 45;
    } else if (sensor >= 27 && sensor <= 34) {
        xOffset = (sensor - 27) * 15;
        yOffset = 60;
    } else if (sensor >= 35 && sensor <= 42) {
        xOffset = (42 - sensor) * 15;
        yOffset = 75;
    } else if (sensor >= 43 && sensor <= 48) {
        xOffset = 15 + (sensor - 43) * 15;
        yOffset = 90;
    } else if (sensor >= 49 && sensor <= 52) {
        xOffset = (52 - sensor) * 15 + 30;
        yOffset = 105;
    } else {
        throw std::out_of_range("CQC sensor index must be in [1, 52]");
    }
}

void CQCSetPositiveColorRange(TH2 *histogram) {
    double minimum = 0.0;
    double maximum = 0.0;
    for (int xBin = 1; xBin <= histogram->GetNbinsX(); ++xBin) {
        for (int yBin = 1; yBin <= histogram->GetNbinsY(); ++yBin) {
            const double value = histogram->GetBinContent(xBin, yBin);
            if (value <= 0.0) continue;
            if (minimum == 0.0 || value < minimum) minimum = value;
            if (value > maximum) maximum = value;
        }
    }
    if (minimum > 0.0 && maximum > minimum) {
        histogram->SetMinimum(minimum);
        histogram->SetMaximum(maximum);
    }
}

#define Sup 250 //Maxmium of histograms
#define VSpd 0.05// Breakdown voltage variance,5%
#define LKGSpd 2.5//leakage current ratio，2.5
#define LCT 0.5 //Breakdown leakage current threshold for per pad (uA)

//TString addshort = "F:\\00LGAD\\process date\\B24\\LGAD-card_B24_1_20250929091255\\20WS0012400001\\20WS20240001"; 

void Card52_v3(TString addshort, double Tp){

    int VBDMin=165; //Break-down Voltage Min
    int VBDMax=195; //Break-down Voltage Max
    int VBDB1=150;
    
    
    std::cout << "You have confirmed temperature :"<< Tp <<endl;

    const bool oldAddDirectory = TH1::AddDirectoryStatus();
    TH1::AddDirectory(kFALSE);

    const TString waferName = gSystem->BaseName(gSystem->WorkingDirectory());
    const TString rootFileName = waferName + ".root";
    TFile rootFile(rootFileName, "RECREATE");
    if (rootFile.IsZombie()) {
        TH1::AddDirectory(oldAddDirectory);
        throw std::runtime_error("Could not create ROOT output file: " + std::string(rootFileName.Data()));
    }

    TDirectory *sensorsDirectory = rootFile.mkdir("Sensors");
    if (!sensorsDirectory) {
        rootFile.Close();
        TH1::AddDirectory(oldAddDirectory);
        throw std::runtime_error("Could not create Sensors directory in ROOT output file");
    }

    int sensorID = 0;
    int channelID = 0;
    double vbdAtTestTemperature_V = 0.0;
    double vbdCorrected20C_V = 0.0;
    double leakageCurrent_A = 0.0;
    TTree channelResults("ChannelResults", "Per-channel CQC Vbd and leakage current");
    channelResults.SetDirectory(&rootFile);
    channelResults.Branch("sensor_id", &sensorID, "sensor_id/I");
    channelResults.Branch("channel_id", &channelID, "channel_id/I");
    channelResults.Branch("vbd_at_test_temperature_V", &vbdAtTestTemperature_V, "vbd_at_test_temperature_V/D");
    channelResults.Branch("vbd_corrected_20C_V", &vbdCorrected20C_V, "vbd_corrected_20C_V/D");
    channelResults.Branch("leakage_current_A", &leakageCurrent_A, "leakage_current_A/D");

    char Jstr[3]={0};

    TGaxis::SetMaxDigits(3);
    
    TString yield[52];
    
    TString VBDPass[52];
    
    double VbdC[52];
    
    double VbdCMin[52];

    double Vbd20dCMin[52];

    double VbdCMax[52];
    
    double RMSVbdC[52];
    
    double ISensorC[52];
    
    double IRMSSensorC[52];
    
    double IMaxSensorC[52] = {0};
    
    double IMinSensorC[52];
    
    double IRtoSensorC[52];
    
    double VbdColumn[52][15] = {{0}};

    double LKGColumn[52][15] = {{0}};
    
    double LKGmax[52];
    
    double LKGmin[52];
    
    TString VBDSPass[52];
    
    TString LKGRMSPass[52];
    for (int w = 0; w < 52; w++){
        IMinSensorC[w] = 10;
        IMaxSensorC[w] = 0;
        Vbd20dCMin[w] = 300;
        VbdCMin[w] = 300;
        VbdCMax[w] = 0;
    }


    for (size_t z = 1; z <= 52; z++){
        TCanvas *c1=new TCanvas("c1","sensorV",800,800);
        TH2 *h1=new TH2D("h1"," ",15,0,15,15,0,15);
        h1->SetContour(30);
        h1->GetZaxis()->SetRangeUser(0,Sup);
        h1->GetXaxis()->SetRange(1,15);
        h1->GetXaxis()->SetNdivisions(-15);
        h1->GetXaxis()->SetLabelFont(42);
        h1->GetXaxis()->SetTitleOffset(1);
        h1->GetXaxis()->SetTitleFont(42);
        h1->GetXaxis()->SetLabelSize(0);
        h1->GetYaxis()->SetLabelSize(0);
        h1->GetYaxis()->SetRange(1,15);
        h1->GetYaxis()->SetNdivisions(-15);
        h1->GetYaxis()->SetLabelFont(42);
        h1->GetYaxis()->SetTitleFont(42);
        h1->GetZaxis()->SetLabelFont(42);
        h1->GetZaxis()->SetTitleOffset(1.5);
        h1->GetZaxis()->SetTitleFont(42);

        c1->SetLeftMargin(0.03);
        c1->SetRightMargin(0.17);
        gPad->Update();

        TH2 *h4=new TH2D("h4"," ",15,0,15,15,0,15);
        h4->SetContour(50);
        h4->GetXaxis()->SetRange(1,15);
        h4->GetXaxis()->SetNdivisions(-15);
        h4->GetXaxis()->SetLabelFont(42);
        h4->GetXaxis()->SetTitleOffset(1);
        h4->GetXaxis()->SetTitleFont(42);
        h4->GetXaxis()->SetLabelSize(0);
        h4->GetYaxis()->SetLabelSize(0);
        h4->GetYaxis()->SetRange(1,15);
        h4->GetYaxis()->SetNdivisions(-15);
        h4->GetYaxis()->SetLabelFont(42);
        h4->GetYaxis()->SetTitleFont(42);
        h4->GetZaxis()->SetLabelFont(42);
        h4->GetZaxis()->SetLabelSize(0.035);
        h4->GetZaxis()->SetTitleOffset(1.5);
        h4->GetZaxis()->SetTitleFont(42);

        TH1*h6=new TH1F("I_leak 15x1"," ",200,0,1e-5);
        TH1*hs=new TH1F("hs","hs",40,0,Sup);
        //cout<<"check1 z is "<<z<<endl;
        for (int i = 1; i < 16; i++){
            snprintf(Jstr, sizeof(Jstr), "%02d", z);
            TString filename =addshort + Jstr;
            TGraph g00(Form(filename+"-%d.csv",i),"%lg,%lg");
            int N = g00.GetN();
            double *x00 = g00.GetX();
            double *y00 = g00.GetY();

            int xOffset, yOffset;
            CQCGetWaferMapOffset(z, xOffset, yOffset);
            for (int k = 0; k < N; k++){
                x00[k] = -x00[k];
                y00[k] = -y00[k];
            }
            TGraph *g1 = new TGraph(N, x00, y00);
            double *x = g1->GetX();
            double *y = g1->GetY();
            int if_fi=0;
            // Fix 2026-09-14 (out-of-bounds read): the old loop bound j<=N-1
            // accessed y[j+1] = y[N], one element past the last point.  On
            // columns without a real crossing (open columns) that read pulls
            // in heap garbage, which can fake a crossing and yield absurd
            // Vbd values (-2.8e110 V seen in batch-2 cross-check).  Bound is
            // now j<N-1 so j+1 stays inside the array, and the scan starts
            // at j=0 so a crossing between the first two points is not missed.
            // A column already above the threshold at the first point is a
            // hard short: record the breakdown at the sweep start.
            if (N > 0 && -y[0] * 1e6 > 15 * LCT) {
                double V_bd = -x[0];
                double V_bd20d = V_bd - (Tp - 20) * 1.1;
                printf("SHORT Sensor %d  col %2d  raw=%7.3f V  T=%4.1f°C  corr=%7.3f V\n",
       z, i, V_bd, Tp, V_bd20d);
                for (int k = 0; k < 15; k++) h1->Fill(i - 0.5, k + 0.5, V_bd20d);
                hs->Fill(V_bd20d);
                VbdColumn[z-1][i-1] = V_bd20d;
                VbdCMin[z-1] = TMath::Min(VbdCMin[z-1], V_bd);
                Vbd20dCMin[z-1] = TMath::Min(Vbd20dCMin[z-1], V_bd20d);
                if_fi = 1;
            }
            for(int j=0;(j<N-1)&&(if_fi==0);j++){
                if ((-y[j] * 1e6 <= 15 * LCT) && (-y[j+1] * 1e6 > 15 * LCT)){
                    double I_bd = 15 * LCT * 1e-6; 
                    double x1 = -x[j+1], x2 = -x[j];  // V
                    double y1 = -y[j+1], y2 = -y[j];  // I
                    // linear interpolation
                    double V_bd = x2 + (x1 - x2) * (I_bd - y2) / (y1 - y2);
                    double V_bd20d = V_bd - (Tp - 20) * 1.1;
                    printf("NEW   Sensor %d  col %2d  raw=%7.3f V  T=%4.1f°C  corr=%7.3f V\n",
       z, i, V_bd, Tp, V_bd20d);
                    cout<<"check2 i is "<<i<<endl;
                    cout<<"check3 Vbd20d is "<<V_bd20d<<endl;
                    for (int k = 0; k < 15; k++) {
                        h1->Fill(i - 0.5, k + 0.5, V_bd20d);
                        printf("col %d  Vbd=%7.2f  count=%d\n", i, V_bd20d, k);
                    }
                    if_fi = 1;
                    hs->Fill(V_bd20d);
                    VbdColumn[z-1][i-1] = V_bd20d;
                    VbdCMin[z-1] = TMath::Min(VbdCMin[z-1], V_bd);
                    Vbd20dCMin[z-1] = TMath::Min(Vbd20dCMin[z-1], V_bd20d);
                    break;
                }
            }
            if (if_fi == 0 && N > 0) {
                double V_bd   = -x[N-1];
                double V_bd20d    = V_bd - (Tp - 20) * 1.1;
                printf("NEW   Sensor %d  col %2d  raw=%7.3f V  T=%4.1f°C  corr=%7.3f V\n",
       z, i, V_bd, Tp, V_bd20d);
                cout << "Sensor " << z << " column " << i << " No breakdown occurred; record the highest voltage Vbd20d=" << V_bd20d << endl;
                //cout << "Sensor " << z << " pad " << i << " No breakdown occurred; record the highest voltage Vbd20d=" << V_bd20d << endl;
                for (int k = 0; k < 15; k++) h1->Fill(i - 0.5, k + 0.5, V_bd20d);
                hs->Fill(V_bd20d);
                VbdColumn[z-1][i-1] = V_bd20d;
                VbdCMin[z-1] = TMath::Min(VbdCMin[z-1], V_bd);
                Vbd20dCMin[z-1] = TMath::Min(Vbd20dCMin[z-1], V_bd20d);
            }
        }

        double VProbe  = 0.8 * VbdCMin[z-1];
        //cout<<"check4 VProbe is "<<VProbe<<endl;
        for (int i = 1; i < 16; i++){
            snprintf(Jstr, sizeof(Jstr), "%02d", z);
            TString filename =addshort + Jstr;
            TGraph g00(Form(filename+"-%d.csv",i),"%lg,%lg");
            int N = g00.GetN();
            double *x00 = g00.GetX();
            double *y00 = g00.GetY();
            for (int k = 0; k < N; k++){
                x00[k] = -x00[k];
                y00[k] = -y00[k];
            }
            TGraph *g1 = new TGraph(N, x00, y00);
            double *x = g1->GetX();
            double *y = g1->GetY();
            int if_fi=0;
            // Fix 2026-09-14: same bound fix as the breakdown scan (j+1 must
            // stay inside the array); j starts at 0 so a VProbe below the
            // second sample point interpolates instead of finding nothing.
            for(int j=0;(j<N-1)&&(if_fi==0);j++){
                if ((-x[j] <= VProbe) && (-x[j+1] > VProbe)) {
                    double x1 = -x[j+1], x2 = -x[j];  // V
                    double y1 = -y[j+1], y2 = -y[j];  // I
                    // linear interpolation
                    LKGColumn[z-1][i-1] = y2 + (y1 - y2) * (VProbe - x2) / (x1 - x2);
                    printf("Sensor %d  col %2d  Vprobe = %7.2f V  Itotal = %12.5e A\n",
       z, i, VProbe, LKGColumn[z-1][i-1]);
                    //cout<<"check5 i is "<<i<<endl;
                    //cout<<"check6 LKG is "<<LKGColumn[z-1][i-1]<<endl;
                    IMaxSensorC[z-1] = TMath::Max(IMaxSensorC[z-1], LKGColumn[z-1][i-1]);
                    //cout<<"check7 IMax is "<<IMaxSensorC[z-1]<<endl;
                    IMinSensorC[z-1] = TMath::Min(IMinSensorC[z-1], LKGColumn[z-1][i-1]);
                    //cout<<"check8 IMin is "<<IMinSensorC[z-1]<<endl;
                    for (int k = 0; k < 15; k++) {
                        h4->Fill(i - 0.5, k + 0.5, LKGColumn[z-1][i-1] / 15);
                    }
                    if_fi = 1;
                    h6->Fill(LKGColumn[z-1][i-1]);
                    break;
                }
            }
            sensorID = static_cast<int>(z);
            channelID = i;
            vbdCorrected20C_V = VbdColumn[z-1][i-1];
            vbdAtTestTemperature_V = vbdCorrected20C_V + (Tp - 20) * 1.1;
            leakageCurrent_A = LKGColumn[z-1][i-1];
            channelResults.Fill();
        }

        IRtoSensorC[z-1]=IMaxSensorC[z-1]/IMinSensorC[z-1];
        //cout<<"check9 IRat is "<<IRtoSensorC[z-1]<<endl;
        RMSVbdC[z-1] = hs->GetRMS();
        VbdC[z-1]=hs->GetMean();

        if (IRtoSensorC[z-1] <=LKGSpd){
            LKGRMSPass[z-1]="Pass";
        }

        if ((RMSVbdC[z-1]/VbdC[z-1]) < VSpd && Vbd20dCMin[z-1]>VBDMin && Vbd20dCMin[z-1]<VBDMax){
            VBDSPass[z-1]="Pass";
        }

        // Establishment of Acceptance Criteria
        if (LKGRMSPass[z-1] == "Pass" && VBDSPass[z-1] == "Pass") {
            yield[z - 1] = "A";
        } else if (LKGRMSPass[z-1] == "Pass" && Vbd20dCMin[z-1]>VBDB1 && Vbd20dCMin[z-1]<VBDMin && RMSVbdC[z-1]/VbdC[z-1] < VSpd) {
            yield[z - 1] = "B1";
        } else if (IRtoSensorC[z-1] < 10 && IRtoSensorC[z-1] > 2.5 && VBDSPass[z-1] == "Pass") {
            yield[z - 1] = "B2";
        } else {
            yield[z - 1] = "C";
        }

        //Drawing the leakage current diagram
        //------------------Filling Over-----------------//
        TCanvas *c00=new TCanvas("c00","I-V Map", 500,500);
        const char *oldFmt = gStyle->GetPaintTextFormat();
        gStyle->SetPaintTextFormat(".1f");
        h1->SetStats(kFALSE);
        h1->Draw("COLZ TEXT");
        gPad->SetGridx(1);
        gPad->SetGridy(1);
        c00->SetRightMargin(0.17);
        gStyle->SetPaintTextFormat(oldFmt);
        h1->SetTitle(" ; ; ;V_{BD} (V)");

        /////////////////////////////////////////// 
        TCanvas *c11=new TCanvas("c11","IMap", 500,500);
        h4->SetStats(kFALSE);
        h4->Draw("COLZ");
        gPad->SetGridx(1);
        gPad->SetGridy(1);
        c11->SetRightMargin(0.17);
        h4->SetTitle(" ; ; ;Leakage Current (A)");

        /////////////////////////////////////////// 
        TCanvas *c3=new TCanvas("c3","I-V", 800,800);
        hs->Draw();


        /////////////////////////////////////////// 
        TCanvas *c7=new TCanvas("c7","I-V-2", 500,500);
        gPad->SetRightMargin(0.12);
        h6->Draw();


        ///////////////////////////////////////////
        TCanvas *c5=new TCanvas("c5","Leakage Current Full", 500,500);
        gPad->SetGridx(1);
        gPad->SetGridy(1);
        gPad->SetRightMargin(0.18);
        gPad->SetLogz();
        h4->SetStats(kFALSE);
        CQCSetPositiveColorRange(h4);
        h4->Draw("COLZ");


        VbdC[z-1]=hs->GetMean();
        RMSVbdC[z-1]=hs->GetRMS();

        ISensorC[z-1]=h6->GetMean();
        IRMSSensorC[z-1]=h6->GetRMS();

        TDirectory *sensorDirectory = sensorsDirectory->mkdir(Form("Sensor_%02d", static_cast<int>(z)));
        if (!sensorDirectory) {
            rootFile.Close();
            TH1::AddDirectory(oldAddDirectory);
            throw std::runtime_error("Could not create sensor directory in ROOT output file");
        }
        sensorDirectory->cd();
        h1->SetName("VbdMap");
        h4->SetName("LeakageMap");
        hs->SetName("VbdHist");
        h6->SetName("LeakageHist");
        h1->Write();
        h4->Write();
        hs->Write();
        h6->Write();
        rootFile.cd();
    }
    
    //save table
    ofstream SensorYield("sensorYield.csv");
    SensorYield << "Sensor"//sensor number
                << ","
                << "Vbd_Average"//sensor number
                << ","
                << "Vbd_Min" //VbdCardMin
                << ","
                << "Vbd_Rms" //VbdCardMean
                << ","
                << "Vbd_Rms_ov_Vbd" //VBD status 
                << ","
                << "Vbd_Status"
                << ","
                << "I_Average"
                << ","
                << "I_Max" //VBD status 
                << ","
                << "I_Min"
                << ","
                << "I_Ratio"
                << ","
                << "Final_Status" //max leakage current
                << endl;
    //form data completion
    for (int i = 0; i < 52; i++){
    SensorYield << i+1 <<"," <<VbdC[i]<< "," << Vbd20dCMin[i]<< "," << RMSVbdC[i] << "," << RMSVbdC[i]/VbdC[i]<< "," << VBDSPass[i] << ","\
                    << ISensorC[i] << ","<<  IMaxSensorC[i]<<","<< IMinSensorC[i] << ","<< IRtoSensorC[i]<< "," << yield[i]\
                    << endl;
}
    //Plot a VBD two-dimensional distribution diagram and sub-diagrams
    TCanvas *VbdmMap = new TCanvas("VbdmMap", "wafer", 800, 800);
    TH2 *hv1 = new TH2D("hv1", " ", 120, 0, 120, 120, 0, 120);
    hv1->GetZaxis()->SetRangeUser(0, Sup);
    hv1->GetXaxis()->SetRange(1, 120);
    hv1->GetXaxis()->SetNdivisions(-1508);
    hv1->GetXaxis()->SetLabelFont(42);
    hv1->GetXaxis()->SetTitleOffset(1);
    hv1->GetXaxis()->SetTitleFont(42);
    hv1->GetXaxis()->SetLabelSize(0);
    hv1->GetYaxis()->SetLabelSize(0);
    hv1->GetYaxis()->SetRange(1, 120);
    hv1->GetYaxis()->SetNdivisions(-1508);
    hv1->GetYaxis()->SetLabelFont(42);
    hv1->GetYaxis()->SetTitleFont(42);
    hv1->GetZaxis()->SetLabelFont(42);
    hv1->GetZaxis()->SetTitleOffset(1.5);
    hv1->GetZaxis()->SetTitleFont(42);
    hv1->SetContour(50); 
    for (int i = 1; i <= 52; i++) {
        int xOffset, yOffset;
        CQCGetWaferMapOffset(i, xOffset, yOffset);
        const double xBase = 0.1;

        for (int j = 0; j < 15; j++) {
            for (int k = 0; k < 15; k++) {
                double x = xOffset + j + xBase;
                double y = 120 - yOffset - (k + 1);
                hv1->Fill(x, y, VbdColumn[i - 1][j]);
            }
        }
    }
    hv1->SetStats(kFALSE);
    hv1->Draw("COLZ");
    gPad->SetGridx(1);
    gPad->SetGridy(1);
    VbdmMap->SetRightMargin(0.17);
    VbdmMap->SaveAs("VbdMap.png");
    rootFile.cd();
    hv1->Write("WaferVbdMap");

    //Draw a two-dimensional leakage current distribution diagram
    TCanvas *LKGnoMap = new TCanvas("LKGnoMap", "wafer2", 800, 800);
    TH2 *hi1 = new TH2D("hv1", " ", 120, 0, 120, 120, 0, 120);
    hi1->GetZaxis()->SetRangeUser(1e-9, 1e-6);
    hi1->GetXaxis()->SetRange(1, 120);
    hi1->GetXaxis()->SetNdivisions(-1508);
    hi1->GetXaxis()->SetLabelFont(42);
    hi1->GetXaxis()->SetTitleOffset(1);
    hi1->GetXaxis()->SetTitleFont(42);
    hi1->GetXaxis()->SetLabelSize(0);
    hi1->GetYaxis()->SetLabelSize(0);
    hi1->GetYaxis()->SetRange(1, 120);
    hi1->GetYaxis()->SetNdivisions(-1508);
    hi1->GetYaxis()->SetLabelFont(42);
    hi1->GetYaxis()->SetTitleFont(42);
    hi1->GetZaxis()->SetLabelFont(42);
    hi1->GetZaxis()->SetTitleOffset(1.5);
    hi1->GetZaxis()->SetTitleFont(42);
    hi1->SetContour(50); 
    for (int i = 1; i <= 52; i++) {
        int xOffset, yOffset;
        CQCGetWaferMapOffset(i, xOffset, yOffset);
        const double xBase = 0.1;

        for (int j = 0; j < 15; j++) {
            for (int k = 0; k < 15; k++) {
                double x = xOffset + j + xBase;
                double y = 120 - yOffset - (k + 1);
                hi1->Fill(x, y, LKGColumn[i - 1][j]);
            }
        }
    }
    gPad->SetLogz();
    hi1->SetStats(kFALSE);
    CQCSetPositiveColorRange(hi1);
    hi1->Draw("COLZ");
    gPad->SetGridx(1);
    gPad->SetGridy(1);
    LKGnoMap->SetRightMargin(0.17);
    LKGnoMap->SaveAs("LKGnoMap.png");
    rootFile.cd();
    hi1->Write("WaferLeakageMap");

    TCanvas *c2full = new TCanvas("c2full", "IV Full", 8000, 4500);
    c2full->Divide(13, 4);
    gPad->SetRightMargin(0.15);
    for (int z = 1; z <= 52; z++){
        c2full->cd(z);
        gPad->DrawFrame(0., 1e-12, Sup, 1e-4);
        gPad->SetLogy(1);
        for (int i = 1; i < 16; i++){
            char Jstr[3]={0};
            snprintf(Jstr, sizeof(Jstr), "%02d", z);
            TString filename =addshort + Jstr;
            TGraph* g111 = new TGraph(Form(filename+"-%d.csv",i),"%lg,%lg");
            g111->SetLineColor(3+i);
            g111->SetTitle(" ; ;Bias (V) ;Leakage Current (A)");
            g111->Draw("same");
        } 
    }
    c2full->SaveAs("IV_Full.png");
    TCanvas *gradeMap = new TCanvas("gradeMap", "Sensor Grade Map", 800, 800);
    gPad->SetGridx(1);
    gPad->SetGridy(1);
    gradeMap->cd();
    gPad->SetGridx(1);
    gPad->SetGridy(1);
    TH2D *base = new TH2D("base", "Sensor Grading Map", 120, 0, 120, 120, 0, 120);
    base->GetXaxis()->SetNdivisions(-1508);
    base->GetYaxis()->SetNdivisions(-1508);
    base->GetXaxis()->SetLabelSize(0);
    base->GetYaxis()->SetLabelSize(0);
    base->SetStats(0);
    base->Draw();
    TLatex *text = new TLatex();
    text->SetTextAlign(22);
    text->SetTextSize(0.025);
    text->SetTextFont(42);

    // Draw the grid colours and number labels for each sensor area.
    for (int i = 1; i <= 52; i++) {
        int xOffset, yOffset;
        CQCGetWaferMapOffset(i, xOffset, yOffset);
        double xBase = 0.1;

        // Determining the background colour
        int color = kGray;
        if (yield[i - 1] == "A") color = kGreen + 1;
        else if (yield[i - 1] == "B1") color = kYellow;
        else if (yield[i - 1] == "B2") color = kOrange + 7;
        else if (yield[i - 1] == "C") color = kRed;

        // Draw a grid background
        for (int j = 0; j < 15; j++) {
            for (int k = 0; k < 15; k++) {
                double x1 = xOffset + j + xBase;
                double y1 = 120 - yOffset - (k + 1);
                double x2 = x1 + 1;
                double y2 = y1 + 1;

                TBox box(x1, y1, x2, y2);
                box.SetFillColor(color);
                box.SetLineColor(color);
                box.Draw("f");
            }
        }

        // Write the number and grade (using a large font to cover the entire cell)
        double xCenter = xOffset + 7.5;
        double yCenter = 120 - yOffset - 7.5;
        text->SetTextColor(kBlack);
        text->DrawLatex(xCenter, yCenter + 2.5, Form("%d", i));
        text->SetTextSize(0.02);
        text->DrawLatex(xCenter, yCenter - 2.5, yield[i - 1]);
        text->SetTextSize(0.025);
    }
    gradeMap->SaveAs("Sensor_Grade_Map.png");

    rootFile.cd();
    channelResults.Write();
    channelResults.SetDirectory(nullptr);
    rootFile.Close();
    TH1::AddDirectory(oldAddDirectory);
    std::cout << "Wrote ROOT output: " << rootFileName << std::endl;
}
