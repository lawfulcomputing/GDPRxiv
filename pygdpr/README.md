<div id="top"></div>




<br />
<div align="center">
  <a href="https://github.com/lawfulcomputing/GDPRxiv/tree/main/pygdpr">
    <img src="images/logo.png" alt="Logo" width="90" height="90">
  </a>

  <h3 align="center">GDPRxiv Crawler (README)</h3>

  <p align="center">
    An efficient tool to crawl GDPR legal documents!
    
  </p>
</div>


## About The Project

With the introduction of the Europeans Union's General Data Protection Regulation (GDPR), there has been an explosion in the number of legal 
documents pertaining to case reviews, analyses, legal decisions, etc... that mark the enforcement of the GDPR.
Additionally, these documents are spread across over 30 Data Protection (DPA) and Supervisory Authorities. As a result, it is 
cumbersome for researchers/legal teams to access and download a large quantity of GDPR documents at once.

To address this, we have created GDPRxiv Crawler, a command-line tool that allows users to efficiently filter and
download GDPR documents. Users may select their desired DPA and document_type, and GDPRxiv Crawler will scrape the web
and download all up-to-date documents. 

Of course, it is impossible to entirely keep up with DPA website redesigns and newly added document categories. 
However, we hope that this tool will eliminate the bulk of the workload and allow users to focus on more important tasks.



### Built With

* [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
* [Selenium](https://www.selenium.dev/)



## Getting Started

### Prerequisites

1. Python >=3.8 is required.


2. WebDriver is required to run Selenium. The code use ChromeDriver, and it support Windows/macOS/Linux OS. Download link: [ChromeDriver](https://chromedriver.chromium.org/downloads).


3. It is strongly recommended that users utilize a virtual environment when installing. 
See below to create and activate one.

_In a directory:_
1. venv:

    ```sh
    virtualenv <virtual env name>
     ```
  
2. Activate the virtual environment:

    ```sh
    source <virtual env name>/bin/activate
    ```

### Installation


1. Clone the repository:
    ```sh
   git clone https://github.com/lawfulcomputing/GDPRxiv.git
   ```
2. Move the downloaded WebDriver inside `GDPRxiv/pygdpr/pygdpr/assets` folder:
    ```sh
   mv <PATH>/chromedriver GDPRxiv/pygdpr/pygdpr/assets/chromedriver
   ```
3. Install project requirements
   ```sh
   cd GDPRxiv/pygdpr
   pip3 install -r requirements.txt
   ```
   This will install the all the required packages; Thereafter you can simply run the project.

## Usage
Downloaded documents will be organized into a set of folders based on DPA and document type.

A file called visitedDocs.txt is always created upon an initial run within a new directory. This file records each downloaded document's unique hash, which allows the tool to avoid overwriting existing documents (if desired) in future runs.

Scrape desired documents:
   ```sh
   cd GDPRxiv/pygdpr
   python gdprCrawler.py --country <country name> --document_type <document type> --path <directory to store documents>
   ```
The same directory can be used for multiple countries: the scraper automatically organizes documents based on country and document type.

Example command:
```sh
 python gdprCrawler.py --country "Austria" --document_type "Decisions" --path "<Your Path>/GDPRxiv/downloaded_documents"
```
&nbsp; 

**Country and document type arguments should be written exactly as they appear below:**

<pre>
SUPPORTED COUNTRIES:     DOCUMENTS TYPES:

        Austria                  Decisions
        Belgium                  Decisions, Annual Reports, Opinions, Guides
        Bulgaria                 Docs (Contains Decisions, Opinions, and Judgements)
        Croatia                  Decisions
        Cyprus                   Decisions, Annual Reports
        Czech Republic           Decisions, Annual Reports, Completed Inspections, Court Rulings, Opinions, Press Releases
        Denmark                  Decisions, Annual Reports, Permissions
        EDPB (Agency)            Decisions, Annual Reports, Guidelines, Letters, Opinions, Recommendations
        Estonia                  Instructions, Prescriptions, Annual Reports
        Finland                  Docs (Contains Advice, Decisions, Guides, Notices)
        France                   Decisions, Notices, Guidelines, Reports
        Germany                  Docs (Contains documents from all the Germany States and Federal DPA)
        Greece                   Decisions, Annual Reports, Guidelines, Opinions, Recommendations
        Hungary                  Decisions, Annual Reports, Notices, Recommendations, Resolutions
        Ireland                  Decisions, Judgements, News, Reports, Blogs, Guidances
        Italy                    Injunctions, Annual Reports, Hearings, Interviews, Newsletters, Publications
        Luxembourg               Decisions, Annual Reports, Opinions
        Malta                    Decisions, Guidelines, News Articles
        Netherlands              Decisions, Opinions, Public Disclosures
        Poland                   Decisions, News
        Portugal                 Decisions, Guidelines, Reports
        Romania                  Docs (Contains Decisions, Reports)
        Slovakia                 Fines (Contains Reports), Opinions
        Slovenia                 Guidelines, Opinions, Reports
        Spain                    Blogs, Decisions, Guides, Infographics, Reports
        Sweden                   Decisions, Guidances, Publications
        United Kingdom           Enforcements, Notices, Reports
</pre>


<p align="right">(<a href="#top">back to top</a>)</p>




